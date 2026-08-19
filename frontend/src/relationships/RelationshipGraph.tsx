import { useEffect, useMemo, useRef, useState } from 'react'
import type { Core, ElementDefinition, EventObjectNode } from 'cytoscape'
import { ExternalLink, LocateFixed } from 'lucide-react'
import { translate } from '../i18n/localization'
import { Link } from 'react-router'

import type { RelationshipsClient, RelationshipGraph as Graph, RelationshipGraphFamily, RelationshipGraphNode, RelationshipGraphSnapshot, RelationshipGraphView, RelationshipScope } from './api'
import './RelationshipGraph.css'

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
  const [graphResult, setGraphResult] = useState<{ key: string; graph: Graph } | null>(null)
  const [depth, setDepth] = useState(rootId ? 2 : 1)
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState(rootId ?? '')
  const [error, setError] = useState('')
  const [savedViews, setSavedViews] = useState<RelationshipGraphView[]>([])
  const [activeView, setActiveView] = useState<RelationshipGraphView | null>(null)
  const [viewName, setViewName] = useState('')
  const [snapshot, setSnapshot] = useState<RelationshipGraphSnapshot | null>(null)
  const requestKey = `${scope.organizationId ?? 'msp'}:${family}:${rootId ?? 'all'}:${depth}`
  const graph = graphResult?.key === requestKey ? graphResult.graph : null

  useEffect(() => {
    const controller = new AbortController()
    if (!client.graph) {
      return () => controller.abort()
    }
    client.graph(scope, family, { rootId, depth, edgeLimit: 150 }, controller.signal)
      .then((result) => { if (!controller.signal.aborted) { setGraphResult({ key: requestKey, graph: result }); setError('') } })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'The relationship map could not be loaded.') })
    return () => controller.abort()
  }, [client, depth, family, requestKey, rootId, scope])

  useEffect(() => {
    if (!client.graphViews) return
    const controller = new AbortController()
    client.graphViews(scope, controller.signal)
      .then((views) => { if (!controller.signal.aborted) setSavedViews(views.filter((view) => view.family === family)) })
      .catch(() => undefined)
    return () => controller.abort()
  }, [client, family, scope])

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
      graphInstance.current.on('select', 'node', (event: EventObjectNode) => setSelectedId(event.target.id()))
      if (activeView) {
        graphInstance.current.nodes().forEach((node) => {
          const position = activeView.positions[node.id()]
          if (position) node.position(position)
        })
        graphInstance.current.fit(undefined, 32)
      }
    })
    return () => { disposed = true; graphInstance.current?.destroy(); graphInstance.current = null }
  }, [activeView, family, graph, visibleEdges, visibleNodes])

  const selected = graph?.nodes.find((node) => node.id === selectedId)
  const selectedPath = selected ? recordPath(selected, scope) : null

  if (!client.graph) return null

  async function saveView() {
    if (!client.saveGraphView || !viewName.trim()) return
    const positions: Record<string, { x: number; y: number }> = {}
    graphInstance.current?.nodes().forEach((node) => { positions[node.id()] = node.position() })
    try {
      const saved = await client.saveGraphView(scope, { name: viewName.trim(), family, root_entity_id: rootId ?? null, depth, edge_limit: 150, positions })
      setSavedViews((current) => [...current, saved].sort((left, right) => left.name.localeCompare(right.name)))
      setActiveView(saved)
      setViewName('')
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The graph view could not be saved.')
    }
  }

  async function retainSnapshot() {
    if (!client.snapshotGraphView || !activeView) return
    try {
      setSnapshot(await client.snapshotGraphView(scope, activeView.id))
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The graph snapshot could not be retained.')
    }
  }

  async function updateLayout() {
    if (!client.updateGraphView || !activeView) return
    const positions: Record<string, { x: number; y: number }> = {}
    graphInstance.current?.nodes().forEach((node) => { positions[node.id()] = node.position() })
    try {
      const updated = await client.updateGraphView(scope, activeView.id, {
        name: activeView.name,
        family,
        root_entity_id: rootId ?? null,
        depth,
        edge_limit: 150,
        positions,
      })
      setActiveView(updated)
      setSavedViews((current) => current.map((view) => view.id === updated.id ? updated : view))
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The graph layout could not be updated.')
    }
  }

  return <section className="content-section relationship-graph" aria-labelledby={`${family}-relationship-graph-heading`}>
    <div className="section-heading relationship-graph-heading"><div><h2 id={`${family}-relationship-graph-heading`}>{heading}</h2><p>Generated from records and relationships visible in this workspace.</p></div><div className="relationship-graph-controls"><label>Depth<select value={depth} onChange={(event) => setDepth(Number(event.target.value))}><option value={1}>1</option><option value={2}>2</option><option value={3}>3</option></select></label><button className="secondary-button" type="button" onClick={() => graphInstance.current?.fit(undefined, 32)}><LocateFixed size={15} aria-hidden="true" />{translate('relationships.fit')}</button></div></div>
    <label className="relationship-graph-search"><span className="sr-only">Filter relationship map</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter visible records" /></label>
    {client.saveGraphView && <div className="relationship-graph-saved"><label>Saved view<select value={activeView?.id ?? ''} onChange={(event) => { const view = savedViews.find((item) => item.id === event.target.value) ?? null; setActiveView(view); if (view) setDepth(view.depth) }}><option value="">Current view</option>{savedViews.map((view) => <option key={view.id} value={view.id}>{view.name}</option>)}</select></label><label>New view name<input maxLength={120} value={viewName} onChange={(event) => setViewName(event.target.value)} /></label><button className="secondary-button" type="button" disabled={!viewName.trim()} onClick={() => { void saveView() }}>{translate('relationships.saveView')}</button>{activeView && client.updateGraphView && <button className="secondary-button" type="button" onClick={() => { void updateLayout() }}>{translate('relationships.updateLayout')}</button>}{activeView && client.snapshotGraphView && <button className="secondary-button" type="button" onClick={() => { void retainSnapshot() }}>{translate('relationships.retainSnapshot')}</button>}</div>}
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
      {snapshot && client.graphSnapshotExportUrl && <div className="relationship-graph-exports" role="status"><span>Snapshot retained.</span>{(['json', 'csv', 'svg'] as const).map((format) => <a key={format} className="secondary-button" href={client.graphSnapshotExportUrl!(scope, snapshot.id, format)}>Download {format.toUpperCase()}</a>)}</div>}
    </>}
  </section>
}
