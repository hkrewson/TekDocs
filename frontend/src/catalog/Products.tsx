import { useEffect, useMemo, useState } from 'react'
import { ChevronRight, FileText, History, Plus, Search, Trash2 } from 'lucide-react'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type {
  CatalogClient,
  CatalogModel,
  CatalogProduct,
  CatalogPublicationChoice,
  DefinitionDraft,
  ModelDraft,
  ProductKind,
  SpecificationDefinition,
  SpecificationProperty,
  SpecificationSchema,
} from './api'

type Tab = 'products' | 'definitions'
type PropertyDraft = { key: string; label: string; type: 'string' | 'integer' | 'number' | 'boolean' | 'choice'; required: boolean; choices: string }

const EMPTY_PRODUCT = { name: '', kind: 'hardware' as ProductKind, description: '' }
const EMPTY_PROPERTY: PropertyDraft = { key: '', label: '', type: 'string', required: false, choices: '' }

function latestDefinitionVersion(definition: SpecificationDefinition) {
  return definition.versions[definition.versions.length - 1]
}

function schemaFromProperties(properties: PropertyDraft[]): SpecificationSchema {
  const mapped: Record<string, SpecificationProperty> = {}
  for (const property of properties) {
    const key = property.key.trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '')
    if (!key) continue
    const choices = property.choices.split(',').map((value) => value.trim()).filter(Boolean)
    mapped[key] = property.type === 'choice'
      ? { type: 'string', title: property.label.trim() || key, enum: choices }
      : { type: property.type, title: property.label.trim() || key }
  }
  return {
    $schema: 'https://json-schema.org/draft/2020-12/schema',
    type: 'object',
    additionalProperties: false,
    properties: mapped,
    required: properties.filter((item) => item.required).map((item) => item.key.trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '')).filter(Boolean),
  }
}

function propertiesFromSchema(schema: SpecificationSchema): PropertyDraft[] {
  const required = new Set(schema.required ?? [])
  const values = Object.entries(schema.properties).map(([key, property]) => ({
    key,
    label: property.title ?? key,
    type: property.enum ? 'choice' as const : property.type === 'array' ? 'string' as const : property.type,
    required: required.has(key),
    choices: property.enum?.join(', ') ?? '',
  }))
  return values.length ? values : [{ ...EMPTY_PROPERTY }]
}

function specificationValue(property: SpecificationProperty, value: string | boolean): unknown {
  if (property.type === 'boolean') return Boolean(value)
  if (property.type === 'integer') return value === '' ? undefined : Number.parseInt(String(value), 10)
  if (property.type === 'number') return value === '' ? undefined : Number(value)
  return value
}

function specificationInputValue(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : ''
}

function ModelForm({ product, definitions, model, saving, onCancel, onSave }: {
  product: CatalogProduct
  definitions: SpecificationDefinition[]
  model?: CatalogModel
  saving: boolean
  onCancel: () => void
  onSave: (draft: ModelDraft) => Promise<void>
}) {
  const applicable = definitions.filter((definition) => definition.product_kind === product.kind)
  const initialVersionId = model?.current_revision.specification_version_id ?? latestDefinitionVersion(applicable[0])?.id ?? ''
  const [draft, setDraft] = useState<ModelDraft>({
    name: model?.name ?? '',
    model_number: model?.model_number ?? '',
    specification_version_id: initialVersionId,
    lifecycle: model?.current_revision.lifecycle ?? 'active',
    specifications: model?.current_revision.specifications ?? {},
    notes: model?.current_revision.notes ?? '',
  })
  const selectedVersion = applicable.flatMap((definition) => definition.versions).find((version) => version.id === draft.specification_version_id)

  return <section className="catalog-editor" aria-labelledby="model-editor-heading">
    <div className="section-heading"><div><h3 id="model-editor-heading">{model ? `Revise ${model.name}` : 'Add model'}</h3><p>Specifications are validated and retained as a new immutable revision.</p></div></div>
    {applicable.length === 0 ? <p className="form-message error" role="alert">Create a {product.kind} specification set before adding a model.</p> : <>
      <div className="catalog-form-grid">
        <label><span>Model name</span><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
        <label><span>Model number or SKU</span><input value={draft.model_number} onChange={(event) => setDraft({ ...draft, model_number: event.target.value })} /></label>
        <label><span>Specification version</span><select value={draft.specification_version_id} onChange={(event) => setDraft({ ...draft, specification_version_id: event.target.value, specifications: {} })}>{applicable.flatMap((definition) => definition.versions.map((version) => <option key={version.id} value={version.id}>{definition.name} · v{version.version}</option>))}</select></label>
        <label><span>Lifecycle</span><select value={draft.lifecycle} onChange={(event) => setDraft({ ...draft, lifecycle: event.target.value as ModelDraft['lifecycle'] })}><option value="active">Active</option><option value="pre_release">Pre-release</option><option value="discontinued">Discontinued</option></select></label>
      </div>
      {selectedVersion && <fieldset className="catalog-spec-fields"><legend>Specifications</legend>{Object.entries(selectedVersion.schema.properties).map(([key, property]) => <label key={key}><span>{property.title ?? key}{selectedVersion.schema.required?.includes(key) ? ' *' : ''}</span>{property.type === 'boolean'
        ? <input type="checkbox" checked={Boolean(draft.specifications[key])} onChange={(event) => setDraft({ ...draft, specifications: { ...draft.specifications, [key]: event.target.checked } })} />
        : property.enum
          ? <select value={specificationInputValue(draft.specifications[key])} onChange={(event) => setDraft({ ...draft, specifications: { ...draft.specifications, [key]: event.target.value } })}><option value="">Choose…</option>{property.enum.map((choice) => <option key={choice}>{choice}</option>)}</select>
          : <input type={property.type === 'integer' || property.type === 'number' ? 'number' : 'text'} value={specificationInputValue(draft.specifications[key])} onChange={(event) => { const value = specificationValue(property, event.target.value); const next = { ...draft.specifications }; if (value === undefined) delete next[key]; else next[key] = value; setDraft({ ...draft, specifications: next }) }} />}</label>)}</fieldset>}
      <label className="catalog-notes"><span>Revision notes</span><textarea rows={3} value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} /></label>
      <div className="form-actions"><button type="button" className="primary-button" disabled={saving || !draft.name || !draft.model_number || !draft.specification_version_id} onClick={() => { void onSave(draft) }}>{saving ? 'Saving…' : model ? 'Create revision' : 'Add model'}</button><button type="button" className="secondary-button" disabled={saving} onClick={onCancel}>Cancel</button></div>
    </>}
  </section>
}

function DefinitionEditor({ definition, saving, onCancel, onSave }: { definition?: SpecificationDefinition; saving: boolean; onCancel: () => void; onSave: (draft: DefinitionDraft) => Promise<void> }) {
  const latest = definition ? latestDefinitionVersion(definition) : undefined
  const [name, setName] = useState(definition?.name ?? '')
  const [kind, setKind] = useState<ProductKind>(definition?.product_kind ?? 'hardware')
  const [properties, setProperties] = useState<PropertyDraft[]>(latest ? propertiesFromSchema(latest.schema) : [{ ...EMPTY_PROPERTY }])
  const schema = schemaFromProperties(properties)
  const valid = name.trim() && Object.keys(schema.properties).length > 0 && properties.every((property) => property.type !== 'choice' || property.choices.split(',').filter((value) => value.trim()).length > 0)

  return <section className="catalog-editor" aria-labelledby="definition-editor-heading"><div className="section-heading"><div><h3 id="definition-editor-heading">{definition ? `New ${definition.name} version` : 'New specification set'}</h3><p>Existing models stay pinned to the version that validated them.</p></div></div><div className="catalog-form-grid"><label><span>Name</span><input value={name} disabled={Boolean(definition)} onChange={(event) => setName(event.target.value)} /></label><label><span>Product type</span><select value={kind} disabled={Boolean(definition)} onChange={(event) => setKind(event.target.value as ProductKind)}><option value="hardware">Hardware</option><option value="software">Software</option></select></label></div><fieldset className="specification-builder"><legend>Specification fields</legend>{properties.map((property, index) => <div className="specification-row" key={index}><label><span>Key</span><input value={property.key} placeholder="port_count" onChange={(event) => setProperties(properties.map((item, itemIndex) => itemIndex === index ? { ...item, key: event.target.value } : item))} /></label><label><span>Label</span><input value={property.label} placeholder="Port count" onChange={(event) => setProperties(properties.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item))} /></label><label><span>Type</span><select value={property.type} onChange={(event) => setProperties(properties.map((item, itemIndex) => itemIndex === index ? { ...item, type: event.target.value as PropertyDraft['type'] } : item))}><option value="string">Text</option><option value="integer">Integer</option><option value="number">Number</option><option value="boolean">Yes / no</option><option value="choice">Choice</option></select></label>{property.type === 'choice' && <label><span>Choices</span><input value={property.choices} placeholder="Indoor, Outdoor" onChange={(event) => setProperties(properties.map((item, itemIndex) => itemIndex === index ? { ...item, choices: event.target.value } : item))} /></label>}<label className="required-check"><input type="checkbox" checked={property.required} onChange={(event) => setProperties(properties.map((item, itemIndex) => itemIndex === index ? { ...item, required: event.target.checked } : item))} /><span>Required</span></label><button type="button" className="icon-button" aria-label={`Remove ${property.label || property.key || 'field'}`} disabled={properties.length === 1} onClick={() => setProperties(properties.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={15} /></button></div>)}<button type="button" className="secondary-button" onClick={() => setProperties([...properties, { ...EMPTY_PROPERTY }])}><Plus size={15} />Add field</button></fieldset><div className="form-actions"><button type="button" className="primary-button" disabled={saving || !valid} onClick={() => { void onSave({ name: name.trim(), product_kind: kind, schema }) }}>{saving ? 'Saving…' : definition ? 'Publish version' : 'Create specification set'}</button><button type="button" className="secondary-button" disabled={saving} onClick={onCancel}>Cancel</button></div></section>
}

export function Products({ workspace, client }: { workspace: WorkspaceContext; client: CatalogClient }) {
  const [tab, setTab] = useState<Tab>('products')
  const [products, setProducts] = useState<CatalogProduct[]>([])
  const [definitions, setDefinitions] = useState<SpecificationDefinition[]>([])
  const [canManage, setCanManage] = useState(false)
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState<ProductKind | ''>('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [productDraft, setProductDraft] = useState<typeof EMPTY_PRODUCT | null>(null)
  const [definitionDraft, setDefinitionDraft] = useState<SpecificationDefinition | 'new' | null>(null)
  const [modelDraft, setModelDraft] = useState<CatalogModel | 'new' | null>(null)
  const [historyId, setHistoryId] = useState<string | null>(null)
  const [publicationChoices, setPublicationChoices] = useState<CatalogPublicationChoice[]>([])
  const [documentDraft, setDocumentDraft] = useState<{ publicationId: string; modelId: string } | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([client.listProducts(workspace, query, kind, controller.signal), client.listDefinitions(workspace, controller.signal)])
      .then(([productResult, definitionResult]) => { setProducts(productResult.results); setDefinitions(definitionResult.results); setCanManage(productResult.can_manage && definitionResult.can_manage); setPhase('ready') })
      .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    return () => controller.abort()
  }, [client, kind, query, refresh, workspace])

  const selected = useMemo(() => products.find((product) => product.id === selectedId) ?? products[0], [products, selectedId])

  async function perform(action: () => Promise<unknown>) {
    setSaving(true); setError(null)
    try { await action(); setProductDraft(null); setDefinitionDraft(null); setModelDraft(null); setDocumentDraft(null); setRefresh((value) => value + 1) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'The catalog change could not be saved.') }
    finally { setSaving(false) }
  }

  async function beginDocumentAssociation() {
    setSaving(true); setError(null)
    try {
      const result = await client.listPublicationChoices(workspace)
      setPublicationChoices(result.results)
      setDocumentDraft({ publicationId: result.results[0]?.id ?? '', modelId: '' })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'STATIC publications could not be loaded.')
    } finally { setSaving(false) }
  }

  return <>
    <header className="page-header"><div><h1>Products</h1><p>Supplier-owned templates and client-visible STATIC documentation retained by client assets.</p></div>{canManage && tab === 'products' && <button className="primary-button" type="button" aria-label={translate('products.new')} title={translate('products.new')} onClick={() => setProductDraft({ ...EMPTY_PRODUCT })}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('products.new')}</span></button>}{canManage && tab === 'definitions' && <button className="primary-button" type="button" aria-label={translate('products.newSpecificationSet')} title={translate('products.newSpecificationSet')} onClick={() => setDefinitionDraft('new')}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('products.newSpecificationSet')}</span></button>}</header>
    {error && <div className="form-message error" role="alert">{error}</div>}
    <div className="mode-tabs catalog-tabs" role="tablist" aria-label="Product catalog sections"><button type="button" role="tab" aria-selected={tab === 'products'} className={tab === 'products' ? 'selected' : ''} onClick={() => setTab('products')}>Products and models</button><button type="button" role="tab" aria-selected={tab === 'definitions'} className={tab === 'definitions' ? 'selected' : ''} onClick={() => setTab('definitions')}>Specification sets</button></div>
    {phase === 'loading' && <section className="content-section" role="status">Loading supplier catalog…</section>}
    {phase === 'error' && <section className="content-section workspace-error" role="alert"><h2>Catalog unavailable</h2><p>The supplier catalog could not be loaded.</p></section>}
    {phase === 'ready' && tab === 'products' && <div className="catalog-layout"><section className="content-section catalog-index"><div className="catalog-filters"><label><span className="sr-only">Search products</span><Search size={16} /><input placeholder="Search products or model numbers" value={query} onChange={(event) => setQuery(event.target.value)} /></label><select aria-label="Filter product type" value={kind} onChange={(event) => setKind(event.target.value as ProductKind | '')}><option value="">All types</option><option value="hardware">Hardware</option><option value="software">Software</option></select></div>{products.length === 0 ? <p className="empty-state">No supplier products match this view.</p> : <ul className="catalog-product-list">{products.map((product) => <li key={product.id}><button type="button" className={selected?.id === product.id ? 'selected' : ''} onClick={() => { setSelectedId(product.id); setDocumentDraft(null) }}><span><strong>{product.name}</strong><small>{product.kind} · {product.models.length} {product.models.length === 1 ? 'model' : 'models'}</small></span><ChevronRight size={16} /></button></li>)}</ul>}</section><section className="content-section catalog-detail">{selected ? <><div className="section-heading"><div><h2>{selected.name}</h2><p>{selected.description || `No description for this ${selected.kind} product.`}</p></div><span>{selected.kind}</span></div>{canManage && <div className="catalog-detail-actions"><button type="button" className="secondary-button" onClick={() => setModelDraft('new')}><Plus size={15} />Add model</button><button type="button" className="icon-button" aria-label={`Archive ${selected.name}`} onClick={() => { if (window.confirm(`Archive ${selected.name} and its models?`)) void perform(() => client.archiveProduct(workspace, selected.id)) }}><Trash2 size={15} /></button></div>}{selected.models.length === 0 ? <p className="empty-state">No models have been defined for this product.</p> : <ul className="catalog-model-list">{selected.models.map((model) => <li key={model.id}><div className="catalog-model-heading"><div><strong>{model.name}</strong><span>{model.model_number} · {model.current_revision.lifecycle.replace('_', '-')} · revision {model.current_revision.revision}</span></div><div>{canManage && <button type="button" className="secondary-button" onClick={() => setModelDraft(model)}>Revise</button>}<button type="button" className="icon-button" aria-expanded={historyId === model.id} aria-label={`${historyId === model.id ? 'Hide' : 'Show'} history for ${model.name}`} onClick={() => setHistoryId(historyId === model.id ? null : model.id)}><History size={15} /></button></div></div><dl className="catalog-specification-list">{Object.entries(model.current_revision.specifications).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{typeof value === 'boolean' ? value ? 'Yes' : 'No' : String(value)}</dd></div>)}</dl>{historyId === model.id && <ol className="catalog-history">{[...model.revisions].reverse().map((revision) => <li key={revision.id}><span>Revision {revision.revision} · {revision.specification_definition_name} v{revision.specification_version}</span><small>{new Date(revision.created_at).toLocaleString()} · {revision.created_by}{revision.notes ? ` · ${revision.notes}` : ''}</small></li>)}</ol>}</li>)}</ul>}{modelDraft && <ModelForm product={selected} definitions={definitions} model={modelDraft === 'new' ? undefined : modelDraft} saving={saving} onCancel={() => setModelDraft(null)} onSave={async (draft) => { await perform(() => modelDraft === 'new' ? client.createModel(workspace, selected.id, draft) : client.reviseModel(workspace, selected.id, modelDraft.id, { ...draft, base_revision_id: modelDraft.current_revision.id })) }} />}<section className="catalog-documents" aria-labelledby="product-documentation-heading"><div className="section-heading"><div><h3 id="product-documentation-heading">Product documentation</h3><p>Only client-visible STATIC publications can follow this product into client assets.</p></div>{canManage && <button type="button" className="secondary-button" disabled={saving} onClick={() => { void beginDocumentAssociation() }}><FileText size={15} />Add publication</button>}</div>{selected.documents.length === 0 ? <p className="empty-state">No retained publications are associated.</p> : <ul className="catalog-document-list">{selected.documents.map((document) => <li key={document.id}><div><strong>{document.title}</strong><span>{document.model_name ? `Model: ${document.model_name}` : 'All product models'} · {document.category}</span></div>{canManage && <button type="button" className="icon-button" aria-label={`Remove ${document.title}`} onClick={() => { void perform(() => client.archiveDocumentAssociation(workspace, selected.id, document.id)) }}><Trash2 size={15} /></button>}</li>)}</ul>}{documentDraft && <div className="catalog-document-form"><label><span>STATIC publication</span><select aria-label="STATIC publication" value={documentDraft.publicationId} onChange={(event) => setDocumentDraft({ ...documentDraft, publicationId: event.target.value })}><option value="">Choose a publication…</option>{publicationChoices.map((publication) => <option key={publication.id} value={publication.id}>{publication.title}</option>)}</select></label><label><span>Applies to</span><select aria-label="Applies to" value={documentDraft.modelId} onChange={(event) => setDocumentDraft({ ...documentDraft, modelId: event.target.value })}><option value="">All models</option>{selected.models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label><div className="form-actions"><button type="button" className="primary-button" disabled={saving || !documentDraft.publicationId} onClick={() => { void perform(() => client.associateDocument(workspace, selected.id, documentDraft.publicationId, documentDraft.modelId || null)) }}>Associate</button><button type="button" className="secondary-button" onClick={() => setDocumentDraft(null)}>Cancel</button></div></div>}</section></> : <p className="empty-state">Choose a product to see its models.</p>}</section></div>}
    {phase === 'ready' && tab === 'definitions' && <section className="content-section"><div className="section-heading"><div><h2>Specification sets</h2><p>Reusable validation contracts. Publishing a new version never changes historical model revisions.</p></div></div>{definitions.length === 0 ? <p className="empty-state">No specification sets have been created.</p> : <ul className="catalog-definition-list">{definitions.map((definition) => { const latest = latestDefinitionVersion(definition); return <li key={definition.id}><div><strong>{definition.name}</strong><span>{definition.product_kind} · {definition.versions.length} {definition.versions.length === 1 ? 'version' : 'versions'} · {Object.keys(latest.schema.properties).length} fields</span></div><div><code>{latest.checksum.slice(0, 12)}</code>{canManage && <button type="button" className="secondary-button" onClick={() => setDefinitionDraft(definition)}>New version</button>}</div></li> })}</ul>}{definitionDraft && <DefinitionEditor definition={definitionDraft === 'new' ? undefined : definitionDraft} saving={saving} onCancel={() => setDefinitionDraft(null)} onSave={async (draft) => { await perform(() => definitionDraft === 'new' ? client.createDefinition(workspace, draft) : client.versionDefinition(workspace, definitionDraft.id, draft.schema)) }} />}</section>}
    {productDraft && <section className="content-section catalog-editor" aria-labelledby="product-editor-heading"><div className="section-heading"><div><h2 id="product-editor-heading">New product</h2><p>Create the stable supplier-owned family before adding individual models.</p></div></div><div className="catalog-form-grid"><label><span>Name</span><input autoFocus value={productDraft.name} onChange={(event) => setProductDraft({ ...productDraft, name: event.target.value })} /></label><label><span>Type</span><select value={productDraft.kind} onChange={(event) => setProductDraft({ ...productDraft, kind: event.target.value as ProductKind })}><option value="hardware">Hardware</option><option value="software">Software</option></select></label><label className="wide-field"><span>Description</span><textarea rows={3} value={productDraft.description} onChange={(event) => setProductDraft({ ...productDraft, description: event.target.value })} /></label></div><div className="form-actions"><button type="button" className="primary-button" disabled={saving || !productDraft.name.trim()} onClick={() => { void perform(async () => { const created = await client.createProduct(workspace, productDraft); setSelectedId(created.id) }) }}>{saving ? 'Saving…' : 'Create product'}</button><button type="button" className="secondary-button" disabled={saving} onClick={() => setProductDraft(null)}>Cancel</button></div></section>}
  </>
}
