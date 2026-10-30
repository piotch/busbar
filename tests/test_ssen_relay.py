import base64
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from busbar import capture_catalogue as capture
from busbar import ssen_relay as relay
from busbar import ssen_relay_handler as handler

ARN = "arn:aws:lambda:eu-west-2:123456789012:function:ssen-relay"
RDF = b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
xmlns:dcat="http://www.w3.org/ns/dcat#">
<dcat:Catalog rdf:about="https://source.example/catalog"/>
<dcat:Dataset rdf:about="https://source.example/dataset"/>
</rdf:RDF>'''


class RelayTests(unittest.TestCase):
    def result(self, **overrides):
        return dict(schema_version=1, status=200, final_url=handler.SOURCE,
                    headers={"Content-Type": "application/rdf+xml"},
                    body_base64=base64.b64encode(RDF).decode(), **overrides)

    def fetch(self, data, function_error=False):
        client = Mock()
        stream = BytesIO(json.dumps(data).encode())
        response = {"StatusCode": 200, "Payload": stream}
        if function_error:
            response["FunctionError"] = "Unhandled"
        client.invoke.return_value = response
        # Also works in the core-only wheel test environment without boto3.
        modules = {
            "boto3": SimpleNamespace(client=Mock(return_value=client)),
            "botocore": SimpleNamespace(),
            "botocore.config": SimpleNamespace(Config=lambda **kwargs: kwargs),
        }
        with patch.dict(sys.modules, modules):
            try:
                return relay.fetch(handler.SOURCE, ARN)
            finally:
                self.assertTrue(stream.closed)

    def test_opt_in_and_host_specific_routing(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(relay.relay_for(handler.SOURCE))
        with patch.dict(os.environ, BUSBAR_SSEN_RELAY_FUNCTION=ARN):
            self.assertEqual(relay.relay_for(handler.SOURCE), ARN)
            self.assertIsNone(relay.relay_for("https://other.example/catalog.rdf"))
        with patch.dict(os.environ, BUSBAR_SSEN_RELAY_FUNCTION=ARN.replace("eu-west-2", "us-east-1")):
            with self.assertRaises(ValueError):
                relay.relay_for(handler.SOURCE)

    def test_endpoint_allowlist(self):
        handler.validate_url(handler.SOURCE + "?page=2")
        for url in ["http://data-api.ssen.co.uk/catalog.rdf",
                    "https://data-api.ssen.co.uk.evil.test/catalog.rdf",
                    "https://data-api.ssen.co.uk/private",
                    handler.SOURCE + "?url=http://169.254.169.254",
                    handler.SOURCE + "?page=0",
                    handler.SOURCE + "?page=2&page=3",
                    handler.SOURCE + "#fragment"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                handler.validate_url(url)

    def test_redirect_rejected_before_request(self):
        with self.assertRaises(ValueError):
            handler.SafeRedirect().redirect_request(
                None, None, 302, "", {}, "https://evil.example/")

    def test_handler_preserves_bytes_and_headers(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.code = 200
        response.url = handler.SOURCE
        response.headers = {"Content-Type": "application/rdf+xml", "ETag": "test"}
        response.read.return_value = RDF
        with patch.object(handler, "build_opener") as opener:
            opener.return_value.open.return_value = response
            data = handler.lambda_handler({}, None)
        self.assertEqual(base64.b64decode(data["body_base64"]), RDF)
        self.assertEqual(data["headers"]["ETag"], "test")
        response.read.return_value = b"x" * (handler.MAX_BYTES + 1)
        with patch.object(handler, "build_opener") as opener:
            opener.return_value.open.return_value = response
            with self.assertRaises(ValueError):
                handler.lambda_handler({}, None)

    def test_client_preserves_bytes(self):
        with self.fetch(self.result()) as response:
            self.assertEqual(response.read(), RDF)
            self.assertEqual(response.status, 200)

    def test_client_rejects_errors_and_bad_payload(self):
        data = self.result()
        data["status"] = 403
        with self.assertRaises(HTTPError) as error:
            self.fetch(data)
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(RuntimeError):
            self.fetch({}, function_error=True)
        data = self.result()
        data["body_base64"] = "!!!"
        with self.assertRaises(ValueError):
            self.fetch(data)

    def test_capture_archives_relay_bytes_and_provenance(self):
        graph, hashes = capture.load_declarations()
        spec = capture.DEFAULT_SPEC.replace("/ukpn/", "/ssen/")
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, BUSBAR_SSEN_RELAY_FUNCTION=ARN), \
                 patch.object(capture, "fetch_via_relay",
                              return_value=relay.RelayResponse(RDF, self.result())), \
                 patch.object(capture, "urlopen") as direct:
                record, _ = capture.capture(graph, hashes, spec, Path(directory))
            direct.assert_not_called()
            self.assertEqual(record["status"], "success")
            self.assertEqual(record["source_url"], handler.SOURCE)
            self.assertEqual(record["acquisition"]["region"], "eu-west-2")
            self.assertEqual((Path(directory) / record["artifact_path"]).read_bytes(), RDF)
            with patch.dict(os.environ, BUSBAR_SSEN_RELAY_FUNCTION=ARN), \
                 patch.object(capture, "fetch_via_relay", side_effect=RuntimeError("failed")), \
                 patch.object(capture, "urlopen") as direct:
                failed, _ = capture.capture(graph, hashes, spec, Path(directory))
            direct.assert_not_called()
            self.assertEqual(failed["status"], "failed")
            self.assertNotIn("dataset_count", failed)
            self.assertEqual(failed["acquisition"]["transport"], "aws-lambda")
