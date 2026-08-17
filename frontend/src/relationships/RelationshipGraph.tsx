import { useEffect, useMemo, useRef, useState } from 'react'
import type { Core, ElementDefinition } from 'cytoscape'
import { ExternalLink, LocateFixed } from 'lucide-react'
import { Link } from 'react-router'

import type { RelationshipsClient, RelationshipGraph as Graph, RelationshipGraphFamily, RelationshipGraphNode, RelationshipScope } from './api'

function recordPath(node: RelationshipGraphNode, scope: RelationshipScope) {
  const prefix = scope.organizationId ? `/workspaces/organizations/${scope.organizationId}` : ''
  if (node.entity_type === 'document') return `${prefix}/documentation?document=${node.id}`
  if (node.entity_type === 'client_asset') return `${prefix}/assets?asset=${node.id}`
  if (node.entity_type.startsWith('network_') || ['wireless_network', 'dns_zone', 'dns_record'].includes(node.entity_type)) return `${prefix}/networks`
  if (node.entity_type === 'site' || node.entity_type === 'location') return `${prefix}/sites`
  return null
}

const nodeColor: Record<RelationshipGraphFamily, string> = { network: '#3f6f75', asset: '#7a623c', document: '#6c5d7d' }

export function RelationshipGraph({ scope, family, client, rootId, heading = 'Relationship map' }: {
  scope: RelationshipScope
  family: RelationshipGraphFamily
  client: RelationshipsClient
  rootId?: string
  heading?: string
}) {
  const container = useRef<HTMLDivElement | null>(null)
  const graphInstance = useRef<Core | null>(null)
  const [graph, setGraph] = useState<Graph | null>(null)
  const [depth, setDepth] = useState(rootId ? 2 : 1)
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState(rootId ?? '')
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setGraph(null)
    if (!client.graph) {
      setError('Relationship maps are unavailable from this connection.')
      return () => controller.abort()
    }
    client.graph(scope, family, { rootId, depth, edgeLimit: 150 }, controller.signal)
      .then((result) => { if (!controller.signal.aborted) { setGraph(result); setError('') } })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'The relationship map could not be loaded.') })
    return () => controller.abort()
  }, [client, depth, family, rootId, scope])

  const visibleNodeIds = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized || !graph) return new Set(graph?.nodes.map((node) => node.id) ?? [])
    const matched = new Set(graph.nodes.filter((node) => `${node.label} ${node.entity_type}`.toLowerCase().includes(normalized)).map((node) => node.id))
    graph.edges.forEach((edge) => {
      if (matched.has(edge.source) || matched.has(edge.target)) { matched.add(edge.source); matched.add(edge.target) }
    })
    return matched
  }, [graph, query])
  const visibleNodes = useMemo(() => graph?.nodes.filter((node) => visibleNodeIds.has(node.id)) ?? [], [graph, visibleNodeIds])
  const visibleEdges = useMemo(() => graph?.edges.filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)) ?? [], [graph, visibleNodeIds])

  useEffect(() => {
    let disposed = false
    if (!container.current || !graph) return
    const elements: ElementDefinition[] = [
      ...visibleNodes.map((node) => ({ data: { id: node.id, label: node.label, root: node.root } })),
      ...visibleEdges.map((edge) => ({ data: { id: edge.id, source: edge.source, target: edge.target, label: edge.label } })),
    ]
    void import('cytoscape').then(({ default: createGraph }) => {
      if (disposed || !container.current) return
      graphInstance.current?.destroy()
      graphInstance.current = createGraph({
        container: container.current,
        elements,
        layout: { name: 'cose', animate: false, randomize: false, nodeRepulsion: () => 7000 },
        style: [
          { selector: 'node', style: { 'background-color': nodeColor[family], label: 'data(label)', color: '#24231f', 'font-size': '11px', 'text-wrap': 'wrap', 'text-max-width': '110px', 'text-valign': 'bottom', 'text-margin-y': 8, width: 28, height: 28 } },
          { selector: 'node[root]', style: { width: 38, height: 38, 'border-width': 3, 'border-color': '#a15c12' } },
          { selector: 'edge', style: { width: 1.5, 'line-color': '#aaa69d', 'target-arrow-color': '#aaa69d', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', label: 'data(label)', 'font-size': '9px', color: '#666159', 'text-background-color': '#f8f7f4', 'text-background-opacity': 1, 'text-background-padding': '2px' } },
          { selector: ':selected', style: { 'border-width': 3, 'border-color': '#24231f' } },
        ],
      })
      graphInstance.current.on('select', 'node', (event) => setSelectedId(event.target.id()))
    })
    return () => { disposed = true; graphInstance.current?.destroy(); graphInstance.current = null }
  }, [family, graph, visibleEdges, visibleNodes])

  const selected = graph?.nodes.find((node) => node.id === selectedId)
  const selectedPath = selected ? recordPath(selected, scope) : null

  if (!client.graph) return null

  return <section className="content-section relationship-graph" aria-labelledby={`${family}-relationship-graph-heading`}>
    <div className="section-heading relationship-graph-heading"><div><h2 id={`${family}-relationship-graph-heading`}>{heading}</h2><p>Generated from records and relationships visible in this workspace.</p></div><div className="relationship-graph-controls"><label>Depth<select value={depth} onChange={(event) => setDepth(Number(event.target.value))}><option value={1}>1</option><option value={2}>2</option><option value={3}>3</option></select></label><button className="secondary-button" type="button" onClick={() => graphInstance.current?.fit(undefined, 32)}><LocateFixed size={15} aria-hidden="true" />Fit</button></div></div>
    <label className="relationship-graph-search"><span className="sr-only">Filter relationship map</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter visible records" /></label>
    {error && <p className="form-error" role="alert">{error}</p>}
    {!graph && !error && <p role="status">Loading relationship map…</p>}
    {graph && graph.nodes.length === 0 && <p className="empty-state">No related records are available in this workspace.</p>}
    {graph && graph.nodes.length > 0 && <>
      <div ref={container} className="relationship-graph-canvas" role="img" aria-label={`${heading}: ${visibleNodes.length} visible records and ${visibleEdges.length} relationships`} />
      {graph.truncated && <p className="relationship-graph-notice">This view reached its relationship limit. Choose a root record or reduce the depth.</p>}
      {selected && <p className="relationship-graph-selection"><strong>{selected.label}</strong><span>{selected.entity_type.replaceAll('_', ' ')}</span>{selectedPath && <Link to={selectedPath}>Open record <ExternalLink size={13} aria-hidden="true" /></Link>}</p>}
      <div className="relationship-graph-table"><table><caption>Accessible relationship list</caption><thead><tr><th>From</th><th>Relationship</th><th>To</th></tr></thead><tbody>{visibleEdges.map((edge) => {
        const source = graph.nodes.find((node) => node.id === edge.source)
        const target = graph.nodes.find((node) => node.id === edge.target)
        return <tr key={edge.id}><td>{source?.label}</td><td>{edge.label}</td><td>{target?.label}</td></tr>
      })}</tbody></table>{visibleEdges.length === 0 && <p className="empty-state">No relationships match this filter.</p>}</div>
    </>}
  </section>
}
