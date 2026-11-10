// Reviewed presentation choices, NOT ontology assertions or equivalences.
// Only seed terms / genuinely shared attributes need manual assignments.
// Properties, subclasses, concepts and instances otherwise follow asserted links.
export const GRID_GROUPS = [
  { id: 'network', title: 'Network structure', color: '#64826c', seeds: [
    'busbar:Site', 'busbar:Substation', 'busbar:TransformerSubstation',
    'busbar:SwitchingStation', 'busbar:GridSupplyPoint', 'busbar:BulkSupplyPoint',
    'busbar:PrimarySubstation', 'busbar:Transformer', 'busbar:Node',
    'busbar:Circuit', 'busbar:TypicalVoltages',
  ] },
  { id: 'projects', title: 'Projects & connections', color: '#8b8760', seeds: [
    'busbar:Project', 'busbar:DistributionProject', 'busbar:TransmissionProject',
    'busbar:REPDProject', 'grid:project-types', 'id:cusc', 'id:ena-ecr',
  ] },
  { id: 'capacity', title: 'Capacity & observations', color: '#66878b', seeds: [
    'busbar:CapacityAssessment', 'busbar:DemandForecast', 'busbar:FlowObservation',
    'busbar:SeasonalRating', 'busbar:SubstationLoad',
  ] },
  { id: 'geography', title: 'Geography & responsibility', color: '#9b805e', seeds: [
    'busbar:Country', 'busbar:DistributionArea', 'busbar:TransmissionArea',
    'busbar:ServiceArea', 'busbar:Organisation', 'busbar:NetworkOperator',
    'busbar:SystemOperator', 'busbar:TransmissionOwner', 'grid:organization-classifications',
  ] },
  { id: 'classifications', title: 'Dataset classifications', color: '#85809b', seeds: [
    'id:dataset-types', 'id:iec-61970-cim', 'id:ofgem-ltds',
    'busbar:describes', 'busbar:localPath',
  ] },
  { id: 'shared', title: 'Shared attributes', color: '#8b9281', seeds: [
    'busbar:TemporalNature', 'busbar:name', 'busbar:timestamp', 'busbar:unit',
    'busbar:latitude', 'busbar:longitude', 'busbar:season', 'busbar:voltageKV',
  ] },
];
