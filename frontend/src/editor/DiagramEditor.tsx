import { Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'

import { translate } from '../i18n/localization'
import { MermaidDiagram } from './MermaidDiagram'
import {
  defaultDiagramDraft,
  diagramSource,
  findMermaidBlocks,
  parseDiagramSource,
  writeMermaidBlock,
  type DiagramDraft,
  type DiagramKind,
} from './diagramBlocks'

export function DiagramEditor({ markdown, onSave, onCancel }: {
  markdown: string
  onSave: (markdown: string) => void
  onCancel: () => void
}) {
  const blocks = useMemo(() => findMermaidBlocks(markdown), [markdown])
  const [target, setTarget] = useState<number | 'new'>(blocks.length ? 0 : 'new')
  const initialSource = target === 'new' ? '' : blocks[target]?.source ?? ''
  const initialDraft = parseDiagramSource(initialSource)
  const [draft, setDraft] = useState<DiagramDraft>(initialDraft ?? defaultDiagramDraft())
  const [rawSource, setRawSource] = useState(initialSource)
  const [sourceMode, setSourceMode] = useState(Boolean(initialSource && !initialDraft))
  const [previewTab, setPreviewTab] = useState<'preview' | 'guide'>('preview')

  const loadTarget = (value: number | 'new') => {
    setTarget(value)
    const source = value === 'new' ? '' : blocks[value]?.source ?? ''
    const parsed = parseDiagramSource(source)
    setDraft(parsed ?? defaultDiagramDraft())
    setRawSource(source)
    setSourceMode(Boolean(source && !parsed))
  }

  const renderedSource = sourceMode ? rawSource : diagramSource(draft)
  const guidedSourceSupported = !rawSource.trim() || parseDiagramSource(rawSource) !== null
  const sourceHasAccessibility = /^\s*accTitle:\s*\S+/im.test(renderedSource)
    && /^\s*accDescr:\s*\S+/im.test(renderedSource)
  const canSave = sourceMode
    ? renderedSource.trim().length > 0 && sourceHasAccessibility
    : Boolean(draft.title.trim() && draft.description.trim() && draft.nodes.length >= 2 && draft.connections.length)

  const updateNode = (index: number, field: 'label' | 'details' | 'shape', value: string) => {
    const nodes = draft.nodes.map((node, nodeIndex) => nodeIndex === index ? { ...node, [field]: value } : node)
    setDraft({ ...draft, nodes })
  }

  const addNode = () => {
    const used = new Set(draft.nodes.map((node) => node.id))
    let number = draft.nodes.length + 1
    while (used.has(`N${number}`)) number += 1
    setDraft({ ...draft, nodes: [...draft.nodes, { id: `N${number}`, label: translate('diagrams.newNode'), details: '', shape: 'system' }] })
  }

  const removeNode = (id: string) => setDraft({
    ...draft,
    nodes: draft.nodes.filter((node) => node.id !== id),
    connections: draft.connections.filter((connection) => connection.from !== id && connection.to !== id),
  })

  const addConnection = () => {
    if (draft.nodes.length < 2) return
    setDraft({
      ...draft,
      connections: [...draft.connections, { from: draft.nodes[0].id, to: draft.nodes[1].id, label: '', style: 'wired' }],
    })
  }

  const save = () => {
    if (!canSave) return
    onSave(writeMermaidBlock(markdown, renderedSource, target === 'new' ? undefined : blocks[target]))
  }

  const handleDialogKey = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') onCancel()
  }

  return <section className="form-overlay" role="dialog" aria-modal="true" aria-labelledby="diagram-editor-title" onKeyDown={handleDialogKey}>
    <div className="record-form diagram-editor">
      <div className="section-heading"><h2 id="diagram-editor-title">{translate(target === 'new' ? 'diagrams.insertTitle' : 'diagrams.editTitle')}</h2></div>
      <div className="diagram-target-row">
        <label>{translate('diagrams.chooseDiagram')}<select autoFocus value={target} onChange={(event) => loadTarget(event.target.value === 'new' ? 'new' : Number(event.target.value))}>
          {blocks.map((_block, index) => <option key={index} value={index}>{translate('diagrams.diagramNumber', { number: index + 1 })}</option>)}
          <option value="new">{translate('diagrams.newDiagram')}</option>
        </select></label>
        <div className="mode-tabs" role="tablist" aria-label={translate('diagrams.editMode')}>
          <button type="button" role="tab" aria-selected={!sourceMode} className={!sourceMode ? 'selected' : ''} disabled={!guidedSourceSupported} title={!guidedSourceSupported ? translate('diagrams.guidedUnavailable') : undefined} onClick={() => { const parsed = parseDiagramSource(rawSource); if (parsed) setDraft(parsed); setSourceMode(false) }}>{translate('diagrams.guided')}</button>
          <button type="button" role="tab" aria-selected={sourceMode} className={sourceMode ? 'selected' : ''} onClick={() => { setRawSource(diagramSource(draft)); setSourceMode(true) }}>{translate('diagrams.source')}</button>
        </div>
      </div>

      <div className="diagram-editor-body">
        <div className="diagram-fields">
          {sourceMode ? <label>{translate('diagrams.sourceLabel')}<textarea className="diagram-source" spellCheck="false" value={rawSource} onChange={(event) => setRawSource(event.target.value)} /></label> : <>
            <div className="form-grid compact">
              <label>{translate('diagrams.type')}<select value={draft.kind} onChange={(event) => setDraft(defaultDiagramDraft(event.target.value as DiagramKind))}><option value="network">{translate('diagrams.network')}</option><option value="flow">{translate('diagrams.flow')}</option></select></label>
              <label>{translate('diagrams.direction')}<select value={draft.direction} onChange={(event) => setDraft({ ...draft, direction: event.target.value as DiagramDraft['direction'] })}><option value="LR">{translate('diagrams.leftToRight')}</option><option value="TD">{translate('diagrams.topToBottom')}</option></select></label>
              <label>{translate('diagrams.title')}<input required maxLength={120} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
              <label>{translate('diagrams.description')}<input required maxLength={300} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
            </div>
            <section className="diagram-list diagram-nodes" aria-labelledby="diagram-nodes-heading">
              <div className="section-heading"><h3 id="diagram-nodes-heading">{translate(draft.kind === 'network' ? 'diagrams.systems' : 'diagrams.steps')}</h3><button className="secondary-button" type="button" onClick={addNode}><Plus size={15} aria-hidden="true" />{translate('diagrams.addNode')}</button></div>
              <ol>{draft.nodes.map((node, index) => <li key={node.id}><span className="diagram-item-id">{node.id}</span><input aria-label={`${translate('diagrams.nodeLabel')} ${index + 1}`} placeholder={translate('diagrams.nodeName')} maxLength={120} value={node.label} onChange={(event) => updateNode(index, 'label', event.target.value)} /><textarea rows={2} aria-label={`${translate('diagrams.nodeDetails')} ${index + 1}`} placeholder={translate('diagrams.nodeDetailsOptional')} maxLength={240} value={node.details} onChange={(event) => updateNode(index, 'details', event.target.value)} /><select aria-label={`${translate('diagrams.nodeShape')} ${index + 1}`} value={node.shape} onChange={(event) => updateNode(index, 'shape', event.target.value)}><option value="system">{translate(draft.kind === 'network' ? 'diagrams.system' : 'diagrams.step')}</option><option value="decision">{translate('diagrams.decision')}</option><option value="terminal">{translate('diagrams.startEnd')}</option><option value="database">{translate('diagrams.database')}</option><option value="document">{translate('diagrams.document')}</option><option value="person">{translate('diagrams.person')}</option><option value="cloud">{translate('diagrams.cloud')}</option><option value="network-device">{translate('diagrams.networkDevice')}</option><option value="input-output">{translate('diagrams.inputOutput')}</option><option value="boundary">{translate('diagrams.boundary')}</option></select><button className="icon-button" type="button" aria-label={`${translate('diagrams.removeNode')} ${node.label}`} onClick={() => removeNode(node.id)}><Trash2 size={15} aria-hidden="true" /></button></li>)}</ol>
            </section>
            <section className="diagram-list diagram-connections" aria-labelledby="diagram-connections-heading">
              <div className="section-heading"><h3 id="diagram-connections-heading">{translate('diagrams.connections')}</h3><button className="secondary-button" type="button" disabled={draft.nodes.length < 2} onClick={addConnection}><Plus size={15} aria-hidden="true" />{translate('diagrams.addConnection')}</button></div>
              <ol>{draft.connections.map((connection, index) => <li key={`${connection.from}-${connection.to}-${index}`}><select aria-label={`${translate('diagrams.from')} ${index + 1}`} value={connection.from} onChange={(event) => setDraft({ ...draft, connections: draft.connections.map((item, itemIndex) => itemIndex === index ? { ...item, from: event.target.value } : item) })}>{draft.nodes.map((node) => <option key={node.id} value={node.id}>{node.label || node.id}</option>)}</select><span aria-hidden="true">→</span><select aria-label={`${translate('diagrams.to')} ${index + 1}`} value={connection.to} onChange={(event) => setDraft({ ...draft, connections: draft.connections.map((item, itemIndex) => itemIndex === index ? { ...item, to: event.target.value } : item) })}>{draft.nodes.map((node) => <option key={node.id} value={node.id}>{node.label || node.id}</option>)}</select><input aria-label={`${translate('diagrams.connectionLabel')} ${index + 1}`} placeholder={translate('diagrams.optionalLabel')} maxLength={80} value={connection.label} onChange={(event) => setDraft({ ...draft, connections: draft.connections.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item) })} /><select aria-label={`${translate('diagrams.connectionStyle')} ${index + 1}`} value={connection.style} onChange={(event) => setDraft({ ...draft, connections: draft.connections.map((item, itemIndex) => itemIndex === index ? { ...item, style: event.target.value as 'wired' | 'wireless' } : item) })}><option value="wired">{translate('diagrams.wired')}</option><option value="wireless">{translate('diagrams.wireless')}</option></select><button className="icon-button" type="button" aria-label={`${translate('diagrams.removeConnection')} ${index + 1}`} onClick={() => setDraft({ ...draft, connections: draft.connections.filter((_item, itemIndex) => itemIndex !== index) })}><Trash2 size={15} aria-hidden="true" /></button></li>)}</ol>
            </section>
          </>}
          {sourceMode && !guidedSourceSupported && <p className="form-message">{translate('diagrams.sourceOnly')}</p>}
          {!sourceHasAccessibility && <p className="form-message error" role="alert">{translate('diagrams.accessibilityRequired')}</p>}
        </div>
        <section className="diagram-preview" aria-label={translate('diagrams.previewPane')}>
          <div className="mode-tabs" role="tablist" aria-label={translate('diagrams.previewTabs')}>
            <button type="button" role="tab" aria-selected={previewTab === 'preview'} className={previewTab === 'preview' ? 'selected' : ''} onClick={() => setPreviewTab('preview')}>{translate('diagrams.preview')}</button>
            <button type="button" role="tab" aria-selected={previewTab === 'guide'} className={previewTab === 'guide' ? 'selected' : ''} onClick={() => setPreviewTab('guide')}>{translate('diagrams.guide')}</button>
          </div>
          {previewTab === 'preview' ? <MermaidDiagram source={renderedSource} index={target === 'new' ? blocks.length : target} showSource={false} showErrorSource={false} /> : <div className="diagram-guide">
            <h3>{translate('diagrams.guideTitle')}</h3>
            <p>{translate('diagrams.guideIntro')}</p>
            <dl>
              <div><dt>{translate('diagrams.guideDirection')}</dt><dd><code>flowchart LR</code> · <code>flowchart TD</code></dd></div>
              <div><dt>{translate('diagrams.guideItems')}</dt><dd><code>{'A@{ shape: cyl, label: "Database" }'}</code></dd></div>
              <div><dt>{translate('diagrams.guideConnections')}</dt><dd><code>A --&gt;|Uses| B</code></dd></div>
              <div><dt>{translate('diagrams.guideAccess')}</dt><dd><code>accTitle:</code> · <code>accDescr:</code></dd></div>
            </dl>
            <p>{translate('diagrams.guideMore')}</p>
          </div>}
        </section>
      </div>
      <div className="form-actions"><button className="secondary-button" type="button" onClick={onCancel}>{translate('common.cancel')}</button><button className="primary-button" type="button" disabled={!canSave} onClick={save}>{translate(target === 'new' ? 'diagrams.insert' : 'diagrams.save')}</button></div>
    </div>
  </section>
}
