import { useCallback, useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, FileText, History, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { QuickDrawer } from '../collections/QuickDrawer'
import '../collections/collections.css'
import { FilterMenu } from '../FilterMenu'
import { translate } from '../i18n/localization'
import type { WorkspaceContext } from '../workspaces/api'
import type {
  CatalogClient,
  CatalogModel,
  CatalogProduct,
  CatalogProductDocument,
  CatalogPublicationChoice,
  DefinitionDraft,
  ModelDraft,
  ProductDraft,
  ProductKind,
  ProductOrdering,
  ProductQuery,
  ProductResult,
  SpecificationDefinition,
  SpecificationProperty,
  SpecificationSchema,
} from './api'

type Tab = 'products' | 'definitions'
type PropertyDraft = { key: string; label: string; type: 'string' | 'integer' | 'number' | 'boolean' | 'choice'; required: boolean; choices: string }

const EMPTY_PRODUCT = { name: '', kind: 'hardware' as ProductKind, description: '', unit_amount: '', currency: 'USD' }
const EMPTY_PROPERTY: PropertyDraft = { key: '', label: '', type: 'string', required: false, choices: '' }
const INITIAL_QUERY: ProductQuery = { q: '', kind: '', ordering: 'name', page: 1, page_size: 25 }

function initialQuery(parameters: URLSearchParams): ProductQuery {
  const ordering = parameters.get('product_order')
  const kind = parameters.get('product_kind')
  const page = Number(parameters.get('product_page'))
  return {
    ...INITIAL_QUERY,
    q: parameters.get('q') ?? '',
    kind: kind === 'hardware' || kind === 'software' ? kind : '',
    ordering: ['name', '-name', 'updated_at', '-updated_at'].includes(ordering ?? '') ? ordering as ProductOrdering : 'name',
    page: Number.isInteger(page) && page > 0 ? page : 1,
  }
}

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

function productKindLabel(kind: ProductKind) {
  return translate(kind === 'hardware' ? 'catalog.hardware' : 'catalog.software')
}

function lifecycleLabel(lifecycle: ModelDraft['lifecycle']) {
  if (lifecycle === 'pre_release') return translate('catalog.preRelease')
  if (lifecycle === 'discontinued') return translate('catalog.discontinued')
  return translate('catalog.active')
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
  const defaultVersion = applicable[0] ? latestDefinitionVersion(applicable[0]) : undefined
  const initialVersionId = model?.current_revision.specification_version_id ?? defaultVersion?.id ?? ''
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
    <div className="section-heading"><div><h3 id="model-editor-heading">{model ? translate('catalog.updateModelHeading', { name: model.name }) : translate('catalog.addModel')}</h3><p>{translate(model ? 'catalog.updateModelHelp' : 'catalog.addModelHelp')}</p></div></div>
    {applicable.length === 0 ? <>
      <p className="form-message error" role="alert">{translate('catalog.modelNeedsTemplate', { type: productKindLabel(product.kind).toLowerCase() })}</p>
      <button type="button" className="secondary-button" onClick={onCancel}>{translate('common.cancel')}</button>
    </> : <>
      <div className="catalog-form-grid">
        <label><span>{translate('catalog.modelName')}</span><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
        <label><span>{translate('catalog.modelNumber')}</span><input value={draft.model_number} onChange={(event) => setDraft({ ...draft, model_number: event.target.value })} /></label>
        <label><span>{translate('catalog.specificationTemplate')}</span><select value={draft.specification_version_id} onChange={(event) => setDraft({ ...draft, specification_version_id: event.target.value, specifications: {} })}>{applicable.flatMap((definition) => definition.versions.map((version) => <option key={version.id} value={version.id}>{translate('catalog.templateVersionOption', { name: definition.name, version: version.version })}</option>))}</select></label>
        <label><span>{translate('catalog.status')}</span><select value={draft.lifecycle} onChange={(event) => setDraft({ ...draft, lifecycle: event.target.value as ModelDraft['lifecycle'] })}><option value="active">{translate('catalog.active')}</option><option value="pre_release">{translate('catalog.preRelease')}</option><option value="discontinued">{translate('catalog.discontinued')}</option></select></label>
      </div>
      {selectedVersion && <fieldset className="catalog-spec-fields"><legend>{translate('catalog.specifications')}</legend>{Object.entries(selectedVersion.schema.properties).map(([key, property]) => <label key={key}><span>{property.title ?? key}{selectedVersion.schema.required?.includes(key) ? ' *' : ''}</span>{property.type === 'boolean'
        ? <input type="checkbox" checked={Boolean(draft.specifications[key])} onChange={(event) => setDraft({ ...draft, specifications: { ...draft.specifications, [key]: event.target.checked } })} />
        : property.enum
          ? <select value={specificationInputValue(draft.specifications[key])} onChange={(event) => setDraft({ ...draft, specifications: { ...draft.specifications, [key]: event.target.value } })}><option value="">{translate('catalog.choose')}</option>{property.enum.map((choice) => <option key={choice}>{choice}</option>)}</select>
          : <input type={property.type === 'integer' || property.type === 'number' ? 'number' : 'text'} value={specificationInputValue(draft.specifications[key])} onChange={(event) => { const value = specificationValue(property, event.target.value); const next = { ...draft.specifications }; if (value === undefined) delete next[key]; else next[key] = value; setDraft({ ...draft, specifications: next }) }} />}</label>)}</fieldset>}
      <label className="catalog-notes"><span>{translate('catalog.changeNotes')}</span><textarea rows={3} value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} /></label>
      <div className="form-actions"><button type="button" className="primary-button" disabled={saving || !draft.name || !draft.model_number || !draft.specification_version_id} onClick={() => { void onSave(draft) }}>{saving ? translate('common.saving') : model ? translate('catalog.saveModelVersion') : translate('catalog.addModel')}</button><button type="button" className="secondary-button" disabled={saving} onClick={onCancel}>{translate('common.cancel')}</button></div>
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

  return <section className="catalog-editor" aria-labelledby="definition-editor-heading">
    <div className="section-heading"><div><h3 id="definition-editor-heading">{definition ? translate('catalog.updateTemplateHeading', { name: definition.name }) : translate('catalog.newTemplateHeading')}</h3><p>{translate('catalog.templateEditorHelp')}</p></div></div>
    <div className="catalog-form-grid">
      <label><span>{translate('catalog.templateName')}</span><input value={name} disabled={Boolean(definition)} onChange={(event) => setName(event.target.value)} /></label>
      <label><span>{translate('catalog.productType')}</span><select value={kind} disabled={Boolean(definition)} onChange={(event) => setKind(event.target.value as ProductKind)}><option value="hardware">{translate('catalog.hardware')}</option><option value="software">{translate('catalog.software')}</option></select></label>
    </div>
    <fieldset className="specification-builder"><legend>{translate('catalog.specificationFields')}</legend>{properties.map((property, index) => <div className="specification-row" key={index}>
      <label><span>{translate('catalog.fieldKey')}</span><input value={property.key} placeholder={translate('catalog.fieldKeyPlaceholder')} onChange={(event) => setProperties(properties.map((item, itemIndex) => itemIndex === index ? { ...item, key: event.target.value } : item))} /></label>
      <label><span>{translate('catalog.fieldLabel')}</span><input value={property.label} placeholder={translate('catalog.fieldLabelPlaceholder')} onChange={(event) => setProperties(properties.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item))} /></label>
      <label><span>{translate('catalog.fieldType')}</span><select value={property.type} onChange={(event) => setProperties(properties.map((item, itemIndex) => itemIndex === index ? { ...item, type: event.target.value as PropertyDraft['type'] } : item))}><option value="string">{translate('catalog.text')}</option><option value="integer">{translate('catalog.integer')}</option><option value="number">{translate('catalog.number')}</option><option value="boolean">{translate('catalog.yesNo')}</option><option value="choice">{translate('catalog.choice')}</option></select></label>
      {property.type === 'choice' && <label><span>{translate('catalog.choices')}</span><input value={property.choices} placeholder={translate('catalog.choicesPlaceholder')} onChange={(event) => setProperties(properties.map((item, itemIndex) => itemIndex === index ? { ...item, choices: event.target.value } : item))} /></label>}
      <label className="required-check"><input type="checkbox" checked={property.required} onChange={(event) => setProperties(properties.map((item, itemIndex) => itemIndex === index ? { ...item, required: event.target.checked } : item))} /><span>{translate('catalog.required')}</span></label>
      <button type="button" className="icon-button" title={translate('catalog.removeField', { name: property.label || property.key || translate('catalog.field') })} aria-label={translate('catalog.removeField', { name: property.label || property.key || translate('catalog.field') })} disabled={properties.length === 1} onClick={() => setProperties(properties.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={15} /></button>
    </div>)}<button type="button" className="secondary-button" onClick={() => setProperties([...properties, { ...EMPTY_PROPERTY }])}><Plus size={15} />{translate('catalog.addField')}</button></fieldset>
    <div className="form-actions"><button type="button" className="primary-button" disabled={saving || !valid} onClick={() => { void onSave({ name: name.trim(), product_kind: kind, schema }) }}>{saving ? translate('common.saving') : definition ? translate('catalog.saveTemplateVersion') : translate('catalog.createTemplate')}</button><button type="button" className="secondary-button" disabled={saving} onClick={onCancel}>{translate('common.cancel')}</button></div>
  </section>
}

function ProductForm({ draft, creating, saving, onChange, onCancel, onSave }: { draft: ProductDraft; creating: boolean; saving: boolean; onChange: (draft: ProductDraft) => void; onCancel: () => void; onSave: () => void }) {
  return <section className="catalog-editor product-editor" aria-labelledby="product-editor-heading">
    <div className="section-heading"><div><h3 id="product-editor-heading">{translate(creating ? 'catalog.productDetails' : 'catalog.editProduct')}</h3><p>{translate(creating ? 'catalog.newProductHelp' : 'catalog.editProductHelp')}</p></div></div>
    <div className="catalog-form-grid"><label><span>{translate('catalog.productName')}</span><input autoFocus value={draft.name} onChange={(event) => onChange({ ...draft, name: event.target.value })} /></label><label><span>{translate('catalog.type')}</span><select value={draft.kind} disabled={!creating} onChange={(event) => onChange({ ...draft, kind: event.target.value as ProductKind })}><option value="hardware">{translate('catalog.hardware')}</option><option value="software">{translate('catalog.software')}</option></select></label><label><span>{translate('catalog.defaultInvoicePrice')}</span><input type="number" min="0" step="0.0001" value={draft.unit_amount ?? ''} onChange={(event) => onChange({ ...draft, unit_amount: event.target.value })} /></label><label><span>{translate('catalog.currency')}</span><input maxLength={3} value={draft.currency ?? ''} onChange={(event) => onChange({ ...draft, currency: event.target.value.toUpperCase() })} /></label><label className="wide-field"><span>{translate('catalog.description')}</span><textarea rows={3} value={draft.description} onChange={(event) => onChange({ ...draft, description: event.target.value })} /></label></div>
    <div className="form-actions"><button type="button" className="primary-button" disabled={saving || !draft.name.trim()} onClick={onSave}>{saving ? translate('common.saving') : translate(creating ? 'catalog.createProduct' : 'catalog.saveProduct')}</button><button type="button" className="secondary-button" disabled={saving} onClick={onCancel}>{translate('common.cancel')}</button></div>
  </section>
}

export function Products({ workspace, client }: { workspace: WorkspaceContext; client: CatalogClient }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>('products')
  const [query, setQuery] = useState<ProductQuery>(() => initialQuery(searchParams))
  const [loaded, setLoaded] = useState<{ scope: string; result: ProductResult } | null>(null)
  const [definitions, setDefinitions] = useState<SpecificationDefinition[]>([])
  const [canManage, setCanManage] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState<{ scope: string; record: CatalogProduct } | null>(null)
  const [drawerErrorId, setDrawerErrorId] = useState<string | null>(null)
  const [productDraft, setProductDraft] = useState<ProductDraft | null>(() => searchParams.get('product') === 'new' ? { ...EMPTY_PRODUCT } : null)
  const [definitionDraft, setDefinitionDraft] = useState<SpecificationDefinition | 'new' | null>(null)
  const [modelDraft, setModelDraft] = useState<CatalogModel | 'new' | null>(null)
  const [historyId, setHistoryId] = useState<string | null>(null)
  const [publicationChoices, setPublicationChoices] = useState<CatalogPublicationChoice[]>([])
  const [documentDraft, setDocumentDraft] = useState<{ publicationId: string; modelId: string } | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [archivingProduct, setArchivingProduct] = useState<CatalogProduct | null>(null)
  const [archivingModel, setArchivingModel] = useState<CatalogModel | null>(null)
  const [removingDocument, setRemovingDocument] = useState<CatalogProductDocument | null>(null)
  const scope = workspace.id
  const drawerId = searchParams.get('product')
  const result = loaded?.scope === scope ? loaded.result : null
  const products = result?.results ?? []
  const listedProduct = drawerId && drawerId !== 'new' ? products.find((product) => product.id === drawerId) : null
  const selected = listedProduct ?? (selectedProduct?.scope === scope && selectedProduct.record.id === drawerId ? selectedProduct.record : null)
  const activeProductDraft = productDraft ?? (drawerId === 'new' ? EMPTY_PRODUCT : null)
  const drawerPhase = drawerErrorId === drawerId ? 'error' : selected || drawerId === 'new' ? 'ready' : 'loading'

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      Promise.all([client.listProducts(workspace, query, controller.signal), client.listDefinitions(workspace, controller.signal)])
        .then(([productResult, definitionResult]) => { if (!controller.signal.aborted) { setLoaded({ scope, result: productResult }); setDefinitions(definitionResult.results); setCanManage(productResult.can_manage && definitionResult.can_manage); setPhase('ready') } })
      .catch(() => { if (!controller.signal.aborted) setPhase('error') })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, query, refresh, scope, workspace])

  useEffect(() => {
    if (!drawerId || drawerId === 'new' || listedProduct) return
    const controller = new AbortController()
    client.retrieveProduct(workspace, drawerId, controller.signal)
      .then((record) => { if (!controller.signal.aborted) { setSelectedProduct({ scope, record }); setDrawerErrorId(null) } })
      .catch(() => { if (!controller.signal.aborted) setDrawerErrorId(drawerId) })
    return () => controller.abort()
  }, [client, drawerId, listedProduct, scope, workspace])

  const updateDrawerUrl = useCallback((id: string | null, replace = false) => {
    const next = new URLSearchParams(searchParams)
    if (id) next.set('product', id); else next.delete('product')
    setSearchParams(next, { replace })
  }, [searchParams, setSearchParams])

  const changeQuery = (changes: Partial<ProductQuery>) => {
    const nextQuery = { ...query, ...changes, page: changes.page ?? 1 }
    const next = new URLSearchParams(searchParams)
    if (nextQuery.q) next.set('q', nextQuery.q); else next.delete('q')
    if (nextQuery.kind) next.set('product_kind', nextQuery.kind); else next.delete('product_kind')
    if (nextQuery.ordering !== 'name') next.set('product_order', nextQuery.ordering); else next.delete('product_order')
    if (nextQuery.page > 1) next.set('product_page', String(nextQuery.page)); else next.delete('product_page')
    setQuery(nextQuery); setSearchParams(next, { replace: true })
  }
  const sort = (field: 'name' | 'updated_at') => changeQuery({ ordering: query.ordering === field ? `-${field}` : field })
  const sortIndicator = (field: string) => query.ordering === field ? <ArrowUp size={13} aria-hidden="true" /> : query.ordering === `-${field}` ? <ArrowDown size={13} aria-hidden="true" /> : null
  const closeDrawer = () => { setProductDraft(null); setModelDraft(null); setDocumentDraft(null); setArchivingProduct(null); setArchivingModel(null); setRemovingDocument(null); updateDrawerUrl(null) }

  async function perform(action: () => Promise<unknown>) {
    setSaving(true); setError(null)
    try {
      await action()
      setProductDraft(null); setDefinitionDraft(null); setModelDraft(null); setDocumentDraft(null)
      setArchivingProduct(null); setArchivingModel(null); setRemovingDocument(null)
      setRefresh((value) => value + 1)
    }
    catch (caught) { setError(caught instanceof Error ? caught.message : translate('catalog.changeFailed')) }
    finally { setSaving(false) }
  }

  async function beginDocumentAssociation() {
    setSaving(true); setError(null)
    try {
      const result = await client.listPublicationChoices(workspace)
      setPublicationChoices(result.results)
      setDocumentDraft({ publicationId: result.results[0]?.id ?? '', modelId: '' })
    } catch {
      setError(translate('catalog.documentsLoadFailed'))
    } finally { setSaving(false) }
  }

  return <>
    <header className="page-header"><div><h1>{translate('catalog.heading', { supplier: workspace.name })}</h1></div>
      {canManage && tab === 'products' && <button className="primary-button" type="button" aria-label={translate('products.new')} title={translate('products.new')} onClick={() => { setProductDraft({ ...EMPTY_PRODUCT }); updateDrawerUrl('new') }}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('products.new')}</span></button>}
      {canManage && tab === 'definitions' && <button className="primary-button" type="button" aria-label={translate('catalog.newTemplate')} title={translate('catalog.newTemplate')} onClick={() => setDefinitionDraft('new')}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('catalog.newTemplate')}</span></button>}
    </header>
    {error && <div className="form-message error" role="alert">{error}</div>}
    <div className="mode-tabs catalog-tabs" role="tablist" aria-label={translate('catalog.sections')}>
      <button type="button" role="tab" aria-selected={tab === 'products'} className={tab === 'products' ? 'selected' : ''} onClick={() => setTab('products')}>{translate('catalog.productsAndModels')}</button>
      <button type="button" role="tab" aria-selected={tab === 'definitions'} className={tab === 'definitions' ? 'selected' : ''} onClick={() => { setTab('definitions'); closeDrawer() }}>{translate('catalog.specificationTemplates')}</button>
    </div>
    {phase === 'loading' && <section className="content-section" role="status">{translate('catalog.loading')}</section>}
    {phase === 'error' && <section className="content-section workspace-error" role="alert"><h2>{translate('catalog.unavailable')}</h2><p>{translate('catalog.loadFailed')}</p></section>}
    {phase === 'ready' && tab === 'products' && <section className="content-section catalog-index" aria-labelledby="product-directory-heading">
        <div className="section-heading"><h2 id="product-directory-heading">{translate('catalog.productDirectory')}</h2><span>{result ? translate('pagination.range', { first: result.count ? (result.page - 1) * result.page_size + 1 : 0, last: Math.min(result.page * result.page_size, result.count), count: result.count }) : translate('common.loading')}</span></div>
        <div className="catalog-filters">
          <label><span className="sr-only">{translate('catalog.search')}</span><Search size={16} /><input type="search" aria-label={translate('catalog.search')} placeholder={translate('catalog.searchPlaceholder')} value={query.q} onChange={(event) => changeQuery({ q: event.target.value })} /></label>
          <FilterMenu groups={[{ kind: 'choices', label: translate('catalog.type'), value: query.kind, choices: [{ value: '', label: translate('catalog.allTypes') }, { value: 'hardware', label: translate('catalog.hardware') }, { value: 'software', label: translate('catalog.software') }], onChange: (value) => changeQuery({ kind: value as ProductKind | '' }) }]} activeCount={query.kind ? 1 : 0} onClear={() => changeQuery({ kind: '' })} menuLabel={translate('catalog.filters')} />
        </div>
        {products.length === 0 ? <p className="empty-state">{translate('catalog.noProducts')}</p> : <div className="people-table-wrap" role="group" aria-label={translate('catalog.productsTable')} tabIndex={0}><table className="people-table"><thead><tr><th scope="col" aria-sort={query.ordering === 'name' ? 'ascending' : query.ordering === '-name' ? 'descending' : 'none'}><button type="button" onClick={() => sort('name')}>{translate('catalog.productName')}{sortIndicator('name')}</button></th><th scope="col">{translate('catalog.type')}</th><th scope="col">{translate('catalog.models')}</th><th scope="col">{translate('catalog.defaultInvoicePrice')}</th><th scope="col" aria-sort={query.ordering === 'updated_at' ? 'ascending' : query.ordering === '-updated_at' ? 'descending' : 'none'}><button type="button" onClick={() => sort('updated_at')}>{translate('catalog.updated')}{sortIndicator('updated_at')}</button></th></tr></thead><tbody>{products.map((product) => <tr key={product.id}><td data-label={translate('catalog.productName')}><button id={`product-row-${product.id}`} className="collection-name" type="button" onClick={() => { setSelectedProduct({ scope, record: product }); setDrawerErrorId(null); updateDrawerUrl(product.id) }}>{product.name}</button><span className="collection-secondary">{product.description || translate('catalog.noDescription', { type: productKindLabel(product.kind).toLowerCase() })}</span></td><td data-label={translate('catalog.type')}>{productKindLabel(product.kind)}</td><td data-label={translate('catalog.models')}>{product.models.length}</td><td data-label={translate('catalog.defaultInvoicePrice')}>{product.unit_amount ? `${product.currency} ${product.unit_amount}` : translate('catalog.noDefaultPrice')}</td><td data-label={translate('catalog.updated')}>{new Date(product.updated_at).toLocaleDateString()}</td></tr>)}</tbody></table></div>}
        {result && result.count > result.page_size && <nav className="people-pagination" aria-label={translate('catalog.productPages')}><button className="secondary-button" type="button" disabled={result.page === 1} onClick={() => changeQuery({ page: result.page - 1 })}><ChevronLeft size={15} aria-hidden="true" />{translate('pagination.previous')}</button><span>{translate('pagination.page', { page: result.page })}</span><button className="secondary-button" type="button" disabled={!result.has_more} onClick={() => changeQuery({ page: result.page + 1 })}>{translate('pagination.next')}<ChevronRight size={15} aria-hidden="true" /></button></nav>}
      </section>}
    {drawerId && tab === 'products' && <QuickDrawer title={drawerId === 'new' ? translate('products.new') : selected?.name ?? translate('catalog.productRecord')} onClose={closeDrawer} returnFocusId={drawerId === 'new' ? undefined : `product-row-${drawerId}`} returnHref={`/workspaces/organizations/${workspace.id}/products`} returnLabel={translate('catalog.backToProducts')}>
      {drawerId === 'new' && activeProductDraft && <ProductForm draft={activeProductDraft} creating saving={saving} onChange={setProductDraft} onCancel={closeDrawer} onSave={() => { void perform(async () => { const created = await client.createProduct(workspace, { ...activeProductDraft, unit_amount: activeProductDraft.unit_amount || null, currency: activeProductDraft.unit_amount ? activeProductDraft.currency : '' }); setSelectedProduct({ scope, record: created }); updateDrawerUrl(created.id, true) }) }} />}
      {drawerId !== 'new' && drawerPhase === 'loading' && <p role="status">{translate('catalog.loadingProduct')}</p>}
      {drawerId !== 'new' && drawerPhase === 'error' && <div className="workspace-error" role="alert"><h3>{translate('catalog.productUnavailable')}</h3><p>{translate('catalog.productUnavailableHelp')}</p></div>}
      {drawerId !== 'new' && drawerPhase === 'ready' && selected && (productDraft ? <ProductForm draft={productDraft} creating={false} saving={saving} onChange={setProductDraft} onCancel={() => setProductDraft(null)} onSave={() => { void perform(async () => { const updated = await client.updateProduct(workspace, selected.id, { name: productDraft.name, description: productDraft.description, unit_amount: productDraft.unit_amount || null, currency: productDraft.unit_amount ? productDraft.currency : '' }); setSelectedProduct({ scope, record: updated }) }) }} /> : <section className="catalog-detail">
        <div className="section-heading"><div><h3>{translate('catalog.productDetails')}</h3><p>{selected.description || translate('catalog.noDescription', { type: productKindLabel(selected.kind).toLowerCase() })}</p></div><span>{productKindLabel(selected.kind)}</span></div>
        {canManage && <div className="catalog-detail-actions"><button type="button" className="secondary-button" onClick={() => setProductDraft({ name: selected.name, kind: selected.kind, description: selected.description, unit_amount: selected.unit_amount ?? '', currency: selected.currency ?? '' })}><Pencil size={15} />{translate('catalog.editProduct')}</button><button type="button" className="secondary-button" onClick={() => setModelDraft('new')}><Plus size={15} />{translate('catalog.addModel')}</button><button type="button" className="icon-button" title={translate('catalog.archiveProduct', { name: selected.name })} aria-label={translate('catalog.archiveProduct', { name: selected.name })} onClick={() => { setArchivingProduct(selected); setArchivingModel(null); setRemovingDocument(null) }}><Trash2 size={15} /></button></div>}
        {selected.models.length === 0 ? <p className="empty-state">{translate('catalog.noModels')}</p> : <ul className="catalog-model-list">{selected.models.map((model) => <li key={model.id}>
          <div className="catalog-model-heading"><div><strong>{model.name}</strong><span>{translate('catalog.modelSummary', { number: model.model_number, status: lifecycleLabel(model.current_revision.lifecycle), version: model.current_revision.revision })}</span></div><div>
            {canManage && <button type="button" className="secondary-button" onClick={() => setModelDraft(model)}>{translate('catalog.updateModel')}</button>}
            <button type="button" className="icon-button" title={translate(historyId === model.id ? 'catalog.hideVersions' : 'catalog.showVersions', { name: model.name })} aria-expanded={historyId === model.id} aria-label={translate(historyId === model.id ? 'catalog.hideVersions' : 'catalog.showVersions', { name: model.name })} onClick={() => setHistoryId(historyId === model.id ? null : model.id)}><History size={15} /></button>
            {canManage && <button type="button" className="icon-button" title={translate('catalog.archiveModel', { name: model.name })} aria-label={translate('catalog.archiveModel', { name: model.name })} onClick={() => { setArchivingModel(model); setArchivingProduct(null); setRemovingDocument(null) }}><Trash2 size={15} /></button>}
          </div></div>
          <dl className="catalog-specification-list">{Object.entries(model.current_revision.specifications).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{typeof value === 'boolean' ? value ? translate('common.yes') : translate('common.no') : String(value)}</dd></div>)}</dl>
          {historyId === model.id && <ol className="catalog-history">{[...model.revisions].reverse().map((revision) => <li key={revision.id}><span>{translate('catalog.modelVersion', { version: revision.revision, template: revision.specification_definition_name, templateVersion: revision.specification_version })}</span><small>{new Date(revision.created_at).toLocaleString()} · {revision.created_by}{revision.notes ? ` · ${revision.notes}` : ''}</small></li>)}</ol>}
        </li>)}</ul>}
        {modelDraft && <ModelForm product={selected} definitions={definitions} model={modelDraft === 'new' ? undefined : modelDraft} saving={saving} onCancel={() => setModelDraft(null)} onSave={async (draft) => { await perform(() => modelDraft === 'new' ? client.createModel(workspace, selected.id, draft) : client.reviseModel(workspace, selected.id, modelDraft.id, { ...draft, base_revision_id: modelDraft.current_revision.id })) }} />}
        {archivingModel && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-model-heading"><div><strong id="archive-model-heading">{translate('catalog.archiveModelHeading', { name: archivingModel.name })}</strong><p>{translate('catalog.archiveModelHelp')}</p></div><div className="form-actions"><button type="button" className="danger-button" disabled={saving} onClick={() => { void perform(() => client.archiveModel(workspace, selected.id, archivingModel.id)) }}>{translate('catalog.archiveModelAction')}</button><button type="button" className="secondary-button" disabled={saving} onClick={() => setArchivingModel(null)}>{translate('common.cancel')}</button></div></div>}
        <section className="catalog-documents" aria-labelledby="product-documentation-heading">
          <div className="section-heading"><div><h3 id="product-documentation-heading">{translate('catalog.documentsHeading')}</h3><p>{translate('catalog.documentsHelp')}</p></div>{canManage && <button type="button" className="secondary-button" disabled={saving} onClick={() => { void beginDocumentAssociation() }}><FileText size={15} />{translate('catalog.addDocument')}</button>}</div>
          {selected.documents.length === 0 ? <p className="empty-state">{translate('catalog.noDocuments')}</p> : <ul className="catalog-document-list">{selected.documents.map((document) => <li key={document.id}><div><strong>{document.title}</strong><span>{document.model_name ? translate('catalog.documentModel', { name: document.model_name }) : translate('catalog.allModels')} · {document.category}</span></div>{canManage && <button type="button" className="icon-button" title={translate('catalog.removeDocument', { name: document.title })} aria-label={translate('catalog.removeDocument', { name: document.title })} onClick={() => { setRemovingDocument(document); setArchivingProduct(null); setArchivingModel(null) }}><Trash2 size={15} /></button>}</li>)}</ul>}
          {documentDraft && <div className="catalog-document-form"><label><span>{translate('catalog.publishedDocument')}</span><select aria-label={translate('catalog.publishedDocument')} value={documentDraft.publicationId} onChange={(event) => setDocumentDraft({ ...documentDraft, publicationId: event.target.value })}><option value="">{translate('catalog.choosePublishedDocument')}</option>{publicationChoices.map((publication) => <option key={publication.id} value={publication.id}>{publication.title}</option>)}</select></label><label><span>{translate('catalog.appliesTo')}</span><select aria-label={translate('catalog.appliesTo')} value={documentDraft.modelId} onChange={(event) => setDocumentDraft({ ...documentDraft, modelId: event.target.value })}><option value="">{translate('catalog.allModels')}</option>{selected.models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label><div className="form-actions"><button type="button" className="primary-button" disabled={saving || !documentDraft.publicationId} onClick={() => { void perform(() => client.associateDocument(workspace, selected.id, documentDraft.publicationId, documentDraft.modelId || null)) }}>{translate('catalog.addDocument')}</button><button type="button" className="secondary-button" onClick={() => setDocumentDraft(null)}>{translate('common.cancel')}</button></div></div>}
          {removingDocument && <div className="archive-confirmation" role="alertdialog" aria-labelledby="remove-product-document-heading"><div><strong id="remove-product-document-heading">{translate('catalog.removeDocumentHeading', { name: removingDocument.title })}</strong><p>{translate('catalog.removeDocumentHelp')}</p></div><div className="form-actions"><button type="button" className="danger-button" disabled={saving} onClick={() => { void perform(() => client.archiveDocumentAssociation(workspace, selected.id, removingDocument.id)) }}>{translate('catalog.removeDocumentAction')}</button><button type="button" className="secondary-button" disabled={saving} onClick={() => setRemovingDocument(null)}>{translate('common.cancel')}</button></div></div>}
        </section>
        {archivingProduct && <div className="archive-confirmation" role="alertdialog" aria-labelledby="archive-product-heading"><div><strong id="archive-product-heading">{translate('catalog.archiveProductHeading', { name: archivingProduct.name })}</strong><p>{translate('catalog.archiveProductHelp')}</p></div><div className="form-actions"><button type="button" className="danger-button" disabled={saving} onClick={() => { void perform(async () => { await client.archiveProduct(workspace, archivingProduct.id); closeDrawer() }) }}>{translate('catalog.archiveProductAction')}</button><button type="button" className="secondary-button" disabled={saving} onClick={() => setArchivingProduct(null)}>{translate('common.cancel')}</button></div></div>}
      </section>)}
    </QuickDrawer>}
    {phase === 'ready' && tab === 'definitions' && <section className="content-section">
      <div className="section-heading"><div><h2>{translate('catalog.specificationTemplates')}</h2><p>{translate('catalog.templatesHelp')}</p></div></div>
      {definitions.length === 0 ? <p className="empty-state">{translate('catalog.noTemplates')}</p> : <ul className="catalog-definition-list">{definitions.map((definition) => { const latest = latestDefinitionVersion(definition); return <li key={definition.id}><div><strong>{definition.name}</strong><span>{productKindLabel(definition.product_kind)} · {translate(definition.versions.length === 1 ? 'catalog.versionCount' : 'catalog.versionCountPlural', { count: definition.versions.length })} · {translate(Object.keys(latest.schema.properties).length === 1 ? 'catalog.fieldCount' : 'catalog.fieldCountPlural', { count: Object.keys(latest.schema.properties).length })}</span></div>{canManage && <button type="button" className="secondary-button" onClick={() => setDefinitionDraft(definition)}>{translate('catalog.updateTemplate')}</button>}</li> })}</ul>}
      {definitionDraft && <DefinitionEditor definition={definitionDraft === 'new' ? undefined : definitionDraft} saving={saving} onCancel={() => setDefinitionDraft(null)} onSave={async (draft) => { await perform(() => definitionDraft === 'new' ? client.createDefinition(workspace, draft) : client.versionDefinition(workspace, definitionDraft.id, draft.schema)) }} />}
    </section>}
  </>
}
