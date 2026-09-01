import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Archive, BookOpenText, CalendarCheck2, Code2, Copy, Download, Ellipsis, ExternalLink, FileCheck2, FileUp, Globe2, Heading, History, Key, Link2, List, ListChecks, ListOrdered, Paperclip, Pencil, Pin, Plus, Quote, RefreshCw, Search, Settings, Share2, ShieldCheck, Table2, Trash2, Type, Unlink, X } from 'lucide-react'
import { FilterMenu } from '../FilterMenu'
import type { FilterMenuGroup } from '../FilterMenu'
import { SanitizedMarkdown } from '../editor/SanitizedMarkdown'
import { translate } from '../i18n/localization'
import type { WorkspaceContext, WorkspaceClient, WorkspaceOption } from '../workspaces/api'
import { browserWorkspaceClient } from '../workspaces/api'
import type { RelationshipsClient } from '../relationships/api'
import { DocumentRelationshipRail } from './DocumentRelationshipRail'
import { DocumentationMaps } from './DocumentationMaps'
import { RelationshipGraph } from '../relationships/RelationshipGraph'
import { browserDocumentsClient, RevisionConflictError } from './api'
import type { DocumentKeyBinding, DocumentKeyReport, WorkspaceKeyBinding } from './api'
import type { BlockKind, BlockLibraryItem, BlockRevision, BlockRevisionDetail, DocumentCategory, DocumentHealthStatus, DocumentInput, DocumentOperationsChoice, DocumentPlacement, DocumentPreflight, DocumentPublication, DocumentPublicationDetail, DocumentRecord, DocumentRemoteObservation, DocumentRemoteSource, DocumentRestructurePreview, DocumentTopicType, DocumentsClient, EntityMentionOption, PlacementAudienceProfile, PublicationAudience, PublicationRetention, ReuseImpact, TemplatePlacementMode, TemplateRollout } from './api'

const Editor = lazy(async () => ({ default: (await import('../editor/EditorSpike')).EditorSpike }))
const PdfViewer = lazy(async () => ({ default: (await import('./PdfViewer')).PdfViewer }))
const categories: { value: DocumentCategory; label: string }[] = [
  { value: 'general', label: 'General' }, { value: 'policy', label: 'Policy' },
  { value: 'procedure', label: 'Procedure' }, { value: 'guide', label: 'Guide' },
  { value: 'reference', label: 'Reference' },
]
const topicTypes: { value: DocumentTopicType; label: string; description: string }[] = [
  { value: 'unstructured', label: translate('documentation.topicUnstructured'), description: translate('documentation.topicUnstructuredHelp') },
  { value: 'procedure', label: translate('documentation.topicProcedure'), description: translate('documentation.topicProcedureHelp') },
  { value: 'troubleshooting', label: translate('documentation.topicTroubleshooting'), description: translate('documentation.topicTroubleshootingHelp') },
  { value: 'reference', label: translate('documentation.topicReference'), description: translate('documentation.topicReferenceHelp') },
  { value: 'system_overview', label: translate('documentation.topicSystemOverview'), description: translate('documentation.topicSystemOverviewHelp') },
  { value: 'change_runbook', label: translate('documentation.topicChangeRunbook'), description: translate('documentation.topicChangeRunbookHelp') },
]
const blockKinds: { value: BlockKind; label: string; description: string }[] = [
  { value: 'rich_text', label: 'Text', description: 'Paragraphs, lists, tables, and callouts' },
  { value: 'heading', label: 'Section heading', description: 'A named section boundary' },
  { value: 'code', label: 'Code', description: 'Commands, configuration, or source' },
  { value: 'url', label: 'URL', description: 'A described external reference' },
  { value: 'document_link', label: 'Document link', description: 'A stable link to another document' },
  { value: 'entity_reference', label: 'TekDocs record', description: 'A person, asset, site, network, or other record' },
  { value: 'file_reference', label: 'File', description: 'A managed attachment reference' },
]

type DocumentPanel = 'details' | 'files' | 'reuse' | 'history' | 'share' | 'relationships' | 'remote' | 'restructure' | 'export' | 'keys' | null
const contentPresets: { label: string; kind: BlockKind; markdown: string; icon: typeof Type }[] = [
  { label: 'Text', kind: 'rich_text', markdown: '', icon: Type },
  { label: 'Heading', kind: 'heading', markdown: '## ', icon: Heading },
  { label: 'Bulleted list', kind: 'rich_text', markdown: '- ', icon: List },
  { label: 'Numbered list', kind: 'rich_text', markdown: '1. ', icon: ListOrdered },
  { label: 'Task list', kind: 'rich_text', markdown: '- [ ] ', icon: ListChecks },
  { label: 'Table', kind: 'rich_text', markdown: '| Column | Column |\n| --- | --- |\n|  |  |', icon: Table2 },
  { label: 'Code', kind: 'code', markdown: '```text\n\n```', icon: Code2 },
  { label: 'Quote', kind: 'rich_text', markdown: '> ', icon: Quote },
]

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Documentation could not be loaded.'
}

function placementAudienceLabel(profile: PlacementAudienceProfile): string {
  if (profile === 'msp_internal') return translate('documentation.audienceMspInternal')
  if (profile === 'client_visible') return translate('documentation.audienceClientVisible')
  return translate('documentation.audienceShared')
}

export function Documentation({ workspace, client = browserDocumentsClient, workspaceClient = browserWorkspaceClient, relationshipsClient, initialDocumentId }: { workspace: WorkspaceContext | null; client?: DocumentsClient; workspaceClient?: WorkspaceClient; relationshipsClient?: RelationshipsClient; initialDocumentId?: string | null }) {
  const requestedDocumentId = initialDocumentId ?? null
  const scope = useMemo(() => workspace ? { organizationId: workspace.id } : {}, [workspace])
  const scopeKey = workspace?.id ?? 'msp'
  const [documentationView, setDocumentationView] = useState<'documents' | 'maps'>('documents')
  const [loaded, setLoaded] = useState<{ key: string; results: DocumentRecord[]; collections: { value: string; count: number }[]; tags: { value: string; count: number }[]; health: { value: string; count: number }[] } | null>(null)
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [selected, setSelected] = useState<DocumentRecord | 'new' | null>(null)
  const [newDocumentMode, setNewDocumentMode] = useState<'write' | 'file'>('write')
  const [newPrimaryFile, setNewPrimaryFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [markdown, setMarkdown] = useState('')
  const [category, setCategory] = useState<DocumentCategory>('general')
  const [topicType, setTopicType] = useState<DocumentTopicType>('unstructured')
  const [isTemplate, setIsTemplate] = useState(false)
  const [libraryVisible, setLibraryVisible] = useState(false)
  const [documentQuery, setDocumentQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<DocumentCategory | ''>('')
  const [templateFilter, setTemplateFilter] = useState<'all' | 'documents' | 'templates'>('all')
  const [collectionFilter, setCollectionFilter] = useState('')
  const [tagFilter, setTagFilter] = useState('')
  const [healthFilter, setHealthFilter] = useState<DocumentHealthStatus | ''>('')
  const [indexMode, setIndexMode] = useState<'browse' | 'health'>('browse')
  const [operationsChoices, setOperationsChoices] = useState<DocumentOperationsChoice[]>([])
  const [operationsDraft, setOperationsDraft] = useState({ ownerId: '', reviewDueOn: '', collection: '', tags: '' })
  const [reviewDraft, setReviewDraft] = useState({ reviewerId: '', note: '' })
  const [decisionDraft, setDecisionDraft] = useState({ decision: 'approved' as 'approved' | 'changes_requested', note: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const [shareQuery, setShareQuery] = useState('')
  const [shareOptions, setShareOptions] = useState<WorkspaceOption[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [history, setHistory] = useState<BlockRevision[]>([])
  const [historyPage, setHistoryPage] = useState(1)
  const [historyCount, setHistoryCount] = useState(0)
  const [historyHasMore, setHistoryHasMore] = useState(false)
  const [historyPhase, setHistoryPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [viewedRevision, setViewedRevision] = useState<BlockRevisionDetail | null>(null)
  const [conflict, setConflict] = useState<RevisionConflictError | null>(null)
  const [sourceDocumentId, setSourceDocumentId] = useState('')
  const [placementMode, setPlacementMode] = useState<'live' | 'pinned'>('live')
  const [placementAudience, setPlacementAudience] = useState<PlacementAudienceProfile>('shared')
  const [audiencePreview, setAudiencePreview] = useState<'all' | PublicationAudience>('all')
  const [newBlockOpen, setNewBlockOpen] = useState(false)
  const [newBlockKind, setNewBlockKind] = useState<BlockKind>('rich_text')
  const [newBlockName, setNewBlockName] = useState('')
  const [newBlockMarkdown, setNewBlockMarkdown] = useState('')
  const [newBlockPosition, setNewBlockPosition] = useState<number | null>(null)
  const [newBlockLibraryVisible, setNewBlockLibraryVisible] = useState(false)
  const [inserterOpen, setInserterOpen] = useState(false)
  const [activePanel, setActivePanel] = useState<DocumentPanel>(null)
  const documentSettingsRef = useRef<HTMLElement>(null)
  const [keyBindings, setKeyBindings] = useState<DocumentKeyBinding[]>([])
  const [keyReport, setKeyReport] = useState<DocumentKeyReport | null>(null)
  const [bindingName, setBindingName] = useState('')
  const [addressableTypes, setAddressableTypes] = useState<string[]>([])
  const [bindingQuery, setBindingQuery] = useState('')
  const [bindingMatches, setBindingMatches] = useState<WorkspaceKeyBinding[]>([])
  const [blockLibraryQuery, setBlockLibraryQuery] = useState('')
  const [blockLibrary, setBlockLibrary] = useState<BlockLibraryItem[]>([])
  const [templateLibrary, setTemplateLibrary] = useState<DocumentRecord[]>([])
  const [templateDraft, setTemplateDraft] = useState<{ source: DocumentRecord; title: string; rules: Record<string, TemplatePlacementMode> } | null>(null)
  const [templateRollout, setTemplateRollout] = useState<TemplateRollout | null>(null)
  const [remoteSourceOpen, setRemoteSourceOpen] = useState(false)
  const [remoteSource, setRemoteSource] = useState<DocumentRemoteSource | null>(null)
  const [remoteSourceDraft, setRemoteSourceDraft] = useState<Pick<DocumentRemoteSource, 'url' | 'source_kind' | 'enabled' | 'check_interval_minutes'>>({ url: '', source_kind: 'auto', enabled: true, check_interval_minutes: 1440 })
  const [remoteObservations, setRemoteObservations] = useState<DocumentRemoteObservation[]>([])
  const [viewedPdf, setViewedPdf] = useState<{ filename: string; url: string } | null>(null)
  const [editingBlock, setEditingBlock] = useState<{ placement: DocumentPlacement; draft: string } | null>(null)
  const [reuseReview, setReuseReview] = useState<{ placementId: string; impact: ReuseImpact; draft: string } | null>(null)
  const [approvedRevisionId, setApprovedRevisionId] = useState<string | null>(null)
  const [mentionQuery, setMentionQuery] = useState('')
  const [mentionOptions, setMentionOptions] = useState<EntityMentionOption[]>([])
  const [editorGeneration, setEditorGeneration] = useState(0)
  const [publicationView, setPublicationView] = useState<{ sourceId: string; phase: 'loading' | 'ready' | 'error'; record?: DocumentPublicationDetail } | null>(null)
  const [publicationForm, setPublicationForm] = useState<{ source: DocumentRecord; reason: string; audience: PublicationAudience; retention: PublicationRetention; reviewOn: string; supersedesId: string | null } | null>(null)
  const [publicationControl, setPublicationControl] = useState<{ action: 'approve' | 'withdraw'; reason: string } | null>(null)
  const [publicationPreflight, setPublicationPreflight] = useState<{ phase: 'loading' | 'ready' | 'error'; report?: DocumentPreflight } | null>(null)
  const [documentCheck, setDocumentCheck] = useState<{ phase: 'loading' | 'ready' | 'error'; report?: DocumentPreflight } | null>(null)
  const [restructurePreview, setRestructurePreview] = useState<DocumentRestructurePreview | null>(null)
  const [restructurePhase, setRestructurePhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [exportAttachmentIds, setExportAttachmentIds] = useState<string[]>([])
  const importInput = useRef<HTMLInputElement>(null)
  const attachmentInput = useRef<HTMLInputElement>(null)
  const newPrimaryFileInput = useRef<HTMLInputElement>(null)
  const replacementFileInput = useRef<HTMLInputElement>(null)
  const insertionMenu = useRef<HTMLDivElement>(null)
  const restoreInsertionPosition = useRef<number | null>(null)
  const openedDeepLink = useRef<string | null>(null)

  useEffect(() => {
    if (inserterOpen) insertionMenu.current?.querySelector<HTMLButtonElement>('.document-insert-types button')?.focus()
  }, [inserterOpen])

  useEffect(() => {
    if (inserterOpen || newBlockOpen || newBlockPosition !== null || restoreInsertionPosition.current === null) return
    const position = restoreInsertionPosition.current
    restoreInsertionPosition.current = null
    window.requestAnimationFrame(() => {
      document.querySelector<HTMLButtonElement>(`[data-insertion-position="${position}"]`)?.focus()
    })
  }, [inserterOpen, newBlockOpen, newBlockPosition])

  useEffect(() => {
    const controller = new AbortController()
    client.list(scope, controller.signal, { q: documentQuery, category: categoryFilter, template: templateFilter, collection: collectionFilter, tag: tagFilter, health: healthFilter })
      .then(async (result) => {
        if (controller.signal.aborted) return
        setLoaded({ key: scopeKey, results: result.results, collections: result.collections ?? [], tags: result.tags ?? [], health: result.health ?? [] })
        setPhase('ready')
        const deepLinkKey = requestedDocumentId ? `${scopeKey}:${requestedDocumentId}` : null
        let deepLinked = requestedDocumentId ? result.results.find((item) => item.id === requestedDocumentId) : null
        if (requestedDocumentId && deepLinkKey && openedDeepLink.current !== deepLinkKey) {
          openedDeepLink.current = deepLinkKey
          if (!deepLinked) {
            try {
              deepLinked = await client.get(scope, requestedDocumentId, controller.signal)
            } catch {
              if (!controller.signal.aborted) setError('That document is not available in this workspace.')
              return
            }
          }
          if (controller.signal.aborted) return
          setSelected(deepLinked)
          setTitle(deepLinked.title)
          setMarkdown(deepLinked.markdown)
          setCategory(deepLinked.category)
          setIsTemplate(deepLinked.is_template)
          setLibraryVisible(deepLinked.library_visible)
          setOperationsDraft({ ownerId: deepLinked.owner_id ?? '', reviewDueOn: deepLinked.review_due_on ?? '', collection: deepLinked.collection ?? '', tags: (deepLinked.tags ?? []).join(', ') })
          if (deepLinked.primary_file?.media_type === 'application/pdf') {
            setViewedPdf({ filename: deepLinked.primary_file.filename, url: client.attachmentDownloadUrl(scope, deepLinked.id, deepLinked.primary_file.id) })
          }
        }
        setError(null)
      })
      .catch((loadError) => { if (!controller.signal.aborted) { setPhase('error'); setError(errorMessage(loadError)) } })
    return () => controller.abort()
  }, [categoryFilter, client, collectionFilter, documentQuery, healthFilter, requestedDocumentId, revision, scope, scopeKey, tagFilter, templateFilter])

  useEffect(() => {
    if (!client.operationsChoices) return
    const controller = new AbortController()
    client.operationsChoices(scope, controller.signal)
      .then((choices) => { if (!controller.signal.aborted) setOperationsChoices(choices) })
      .catch(() => { if (!controller.signal.aborted) setOperationsChoices([]) })
    return () => controller.abort()
  }, [client, scope])

  useEffect(() => {
    if (!workspace) return
    const controller = new AbortController()
    client.listTemplateLibrary(scope, controller.signal)
      .then((result) => { if (!controller.signal.aborted) setTemplateLibrary(result.results) })
      .catch(() => { if (!controller.signal.aborted) setTemplateLibrary([]) })
    return () => controller.abort()
  }, [client, revision, scope, workspace])

  useEffect(() => {
    if (workspace || !shareQuery.trim() || selected === null || selected === 'new') return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      workspaceClient.searchOrganizations(shareQuery, 1, controller.signal, 'client')
        .then((result) => { if (!controller.signal.aborted) setShareOptions(result.results) })
        .catch(() => { if (!controller.signal.aborted) setShareOptions([]) })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [selected, shareQuery, workspace, workspaceClient])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      if (!bindingQuery.trim() || activePanel !== 'keys') { setBindingMatches([]); return }
      client.browseKeyBindings(scope, bindingQuery, controller.signal)
        .then((result) => { if (!controller.signal.aborted) setBindingMatches(result.results) })
        .catch(() => { if (!controller.signal.aborted) setBindingMatches([]) })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [activePanel, bindingQuery, client, scope])

  useEffect(() => {
    if (activePanel !== 'details') return
    documentSettingsRef.current?.scrollIntoView?.({ block: 'start' })
    documentSettingsRef.current?.focus({ preventScroll: true })
  }, [activePanel])

  useEffect(() => {
    if (!mentionQuery.trim() || !selected) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.searchMentionEntities(scope, mentionQuery, controller.signal)
        .then((result) => { if (!controller.signal.aborted) setMentionOptions(result.results) })
        .catch(() => { if (!controller.signal.aborted) setMentionOptions([]) })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [client, mentionQuery, scope, selected])

  useEffect(() => {
    if (!selected || selected === 'new') return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      client.searchBlockLibrary(scope, blockLibraryQuery, controller.signal)
        .then((result) => { if (!controller.signal.aborted) setBlockLibrary(result.results.filter((item) => item.source_document_id !== selected.id)) })
        .catch(() => { if (!controller.signal.aborted) setBlockLibrary([]) })
    }, 180)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [blockLibraryQuery, client, scope, selected])

  const results = loaded?.key === scopeKey ? loaded.results : []
  const visiblePhase = loaded?.key === scopeKey ? phase : 'loading'
  const resetRevisionUi = () => { setHistoryOpen(false); setHistory([]); setHistoryPhase('idle'); setViewedRevision(null); setViewedPdf(null); setConflict(null); setReuseReview(null); setApprovedRevisionId(null); setMentionQuery(''); setMentionOptions([]); setEditingBlock(null); setNewBlockOpen(false); setInserterOpen(false); setActivePanel(null); setNewBlockMarkdown(''); setNewBlockName(''); setNewBlockPosition(null); setNewBlockLibraryVisible(false); setBlockLibraryQuery(''); setBlockLibrary([]); setTemplateRollout(null); setRestructurePreview(null); setRestructurePhase('idle'); setExportAttachmentIds([]); setKeyBindings([]); setKeyReport(null); setBindingName(''); setAddressableTypes([]); setBindingQuery(''); setBindingMatches([]); setPlacementAudience('shared'); setAudiencePreview('all'); setDocumentCheck(null) }
  const open = (document: DocumentRecord) => { resetRevisionUi(); setPublicationView(null); setPublicationForm(null); setPublicationControl(null); setSelected(document); setTitle(document.title); setMarkdown(document.markdown); setCategory(document.category); setTopicType(document.topic_type ?? 'unstructured'); setIsTemplate(document.is_template); setLibraryVisible(document.library_visible); setOperationsDraft({ ownerId: document.owner_id ?? '', reviewDueOn: document.review_due_on ?? '', collection: document.collection ?? '', tags: (document.tags ?? []).join(', ') }); setReviewDraft({ reviewerId: document.reviewer_id ?? '', note: '' }); setDecisionDraft({ decision: 'approved', note: '' }); setMessage(null); setError(null); setShareQuery(''); setSourceDocumentId(''); setPlacementMode('live'); setPlacementAudience('shared'); setAudiencePreview('all'); setExportAttachmentIds([]); if (document.primary_file?.media_type === 'application/pdf') setViewedPdf({ filename: document.primary_file.filename, url: client.attachmentDownloadUrl(scope, document.id, document.primary_file.id) }) }
  const create = () => { resetRevisionUi(); setPublicationView(null); setPublicationForm(null); setPublicationControl(null); setSelected('new'); setNewDocumentMode('write'); setNewPrimaryFile(null); setTitle(''); setMarkdown(''); setCategory('general'); setTopicType('unstructured'); setIsTemplate(false); setLibraryVisible(false); setMessage(null); setError(null) }
  const close = () => { resetRevisionUi(); setSelected(null); setPublicationView(null); setPublicationForm(null); setPublicationControl(null); setShareQuery(''); setShareOptions([]) }
  const openPublication = async (document: DocumentRecord, publication: DocumentPublication) => {
    resetRevisionUi(); setSelected(null); setPublicationForm(null); setPublicationControl(null); setPublicationView({ sourceId: document.id, phase: 'loading' }); setError(null); setMessage(null)
    try { setPublicationView({ sourceId: document.id, phase: 'ready', record: await client.getPublication(scope, document.id, publication.id) }) }
    catch (publicationError) { setPublicationView({ sourceId: document.id, phase: 'error' }); setError(errorMessage(publicationError)) }
  }
  const save = async (skipImpactReview = false) => {
    if (!selected || !title.trim()) return
    setSaving(true); setError(null)
    const input: DocumentInput = { title: title.trim(), markdown, category, topic_type: topicType, is_template: isTemplate, library_visible: libraryVisible }
    try {
      if (selected !== 'new' && markdown !== selected.markdown && !skipImpactReview && approvedRevisionId !== selected.current_revision_id) {
        const primary = selected.placements.find((placement) => placement.is_primary)
        if (primary) {
          const impact = await client.getReuseImpact(scope, selected.id, primary.id)
          if (impact.live_audience_count > 1) {
            setReuseReview({ placementId: primary.id, impact, draft: markdown })
            setMessage('Review the audiences below before saving this shared revision.')
            return
          }
        }
      }
      const record = selected === 'new'
        ? await client.create(scope, input)
        : await client.update(scope, selected.id, { ...input, base_revision_id: selected.current_revision_id })
      setSelected(record); setTitle(record.title); setMarkdown(record.markdown); setCategory(record.category); setTopicType(record.topic_type ?? 'unstructured'); setIsTemplate(record.is_template); setLibraryVisible(record.library_visible); setConflict(null); setMessage(`Document saved as revision ${record.revision_number}.`); setRevision((value) => value + 1)
      if (historyOpen) void loadHistory(record)
    } catch (saveError) {
      if (saveError instanceof RevisionConflictError) setConflict(saveError)
      else setError(errorMessage(saveError))
    } finally { setSaving(false) }
  }
  const saveOperations = async () => {
    if (!selected || selected === 'new' || !client.updateOperations) return
    setSaving(true); setError(null)
    try {
      const record = await client.updateOperations(scope, selected.id, {
        owner_id: operationsDraft.ownerId || null,
        review_due_on: operationsDraft.reviewDueOn || null,
        collection: operationsDraft.collection.trim(),
        tags: operationsDraft.tags.split(',').map((tag) => tag.trim()).filter(Boolean),
      })
      setSelected(record); setMessage(translate('documentation.operationsSaved')); setRevision((value) => value + 1)
    } catch (operationsError) { setError(errorMessage(operationsError)) } finally { setSaving(false) }
  }
  const requestReview = async () => {
    if (!selected || selected === 'new' || !client.requestReview || !reviewDraft.reviewerId) return
    setSaving(true); setError(null)
    try {
      const record = await client.requestReview(scope, selected.id, reviewDraft.reviewerId, reviewDraft.note)
      setSelected(record); setReviewDraft({ reviewerId: record.reviewer_id ?? '', note: '' }); setMessage(translate('documentation.reviewRequested')); setRevision((value) => value + 1)
    } catch (reviewError) { setError(errorMessage(reviewError)) } finally { setSaving(false) }
  }
  const decideReview = async () => {
    if (!selected || selected === 'new' || !client.decideReview || !decisionDraft.note.trim()) return
    setSaving(true); setError(null)
    try {
      const record = await client.decideReview(scope, selected.id, decisionDraft.decision, decisionDraft.note.trim())
      setSelected(record); setDecisionDraft({ decision: 'approved', note: '' }); setMessage(decisionDraft.decision === 'approved' ? translate('documentation.reviewApproved') : translate('documentation.changesRequested')); setRevision((value) => value + 1)
    } catch (decisionError) { setError(errorMessage(decisionError)) } finally { setSaving(false) }
  }
  const createFileBackedDocument = async () => {
    if (selected !== 'new' || !title.trim() || !newPrimaryFile) return
    setSaving(true); setError(null)
    try {
      const record = await client.createFileBacked(scope, { title: title.trim(), notes: markdown, category, file: newPrimaryFile })
      setSelected(record); setNewPrimaryFile(null); setTitle(record.title); setMarkdown(record.markdown); setMessage('File-backed document created.'); setRevision((value) => value + 1)
      if (record.primary_file?.media_type === 'application/pdf') setViewedPdf({ filename: record.primary_file.filename, url: client.attachmentDownloadUrl(scope, record.id, record.primary_file.id) })
    } catch (creationError) { setError(errorMessage(creationError)) } finally { setSaving(false) }
  }
  const archive = async () => {
    if (!selected || selected === 'new') return
    if (!window.confirm(`Archive “${selected.title}”?`)) return
    setSaving(true); setError(null)
    try { await client.archive(scope, selected.id); close(); setMessage('Document archived.'); setRevision((value) => value + 1) }
    catch (archiveError) { setError(errorMessage(archiveError)) } finally { setSaving(false) }
  }
  const share = async (organization: WorkspaceOption) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try { await client.addReference(selected.id, organization.id); setMessage(`Reference added to ${organization.name}.`); setShareQuery(''); setShareOptions([]) }
    catch (shareError) { setError(errorMessage(shareError)) } finally { setSaving(false) }
  }
  const loadHistory = async (document = selected, page = 1) => {
    if (!document || document === 'new') return
    setHistoryOpen(true); setHistoryPhase('loading'); setViewedRevision(null)
    try {
      const result = await client.listRevisions(scope, document.id, page)
      setHistory(result.results); setHistoryPage(result.page); setHistoryCount(result.count); setHistoryHasMore(result.has_more); setHistoryPhase('ready')
    }
    catch (historyError) { setHistoryPhase('error'); setError(errorMessage(historyError)) }
  }
  const inspectRevision = async (revisionRecord: BlockRevision) => {
    if (!selected || selected === 'new') return
    try { setViewedRevision(await client.getRevision(scope, selected.id, revisionRecord.id)) }
    catch (historyError) { setError(errorMessage(historyError)) }
  }
  const acknowledgeConflict = () => {
    if (!conflict || !selected || selected === 'new') return
    const current = conflict.payload.current_revision
    setSelected({ ...selected, current_revision_id: current.id, revision_number: current.revision_number, checksum: current.checksum })
    setConflict(null)
    setMessage('Conflict acknowledged. Reconcile the draft with the shown server changes before saving.')
  }
  const applyCompositionRecord = (record: DocumentRecord, status: string) => {
    setSelected(record); setMarkdown(record.markdown); setMessage(status); setError(null); setRevision((value) => value + 1)
  }
  const previewRestructure = async () => {
    if (!selected || selected === 'new') return
    setActivePanel('restructure'); setRestructurePhase('loading'); setRestructurePreview(null); setError(null)
    try { setRestructurePreview(await client.previewRestructure(scope, selected.id)); setRestructurePhase('ready') }
    catch (previewError) { setRestructurePhase('error'); setError(errorMessage(previewError)) }
  }
  const applyRestructure = async () => {
    if (!selected || selected === 'new' || !restructurePreview?.eligible || !restructurePreview.base_revision_id) return
    setSaving(true); setError(null)
    try {
      const result = await client.applyRestructure(scope, selected.id, restructurePreview.base_revision_id)
      applyCompositionRecord(result.document, `Content separated into ${result.section_count} editable sections.`)
      setActivePanel(null); setRestructurePreview(null); setRestructurePhase('idle')
    } catch (conversionError) {
      if (conversionError instanceof RevisionConflictError) setConflict(conversionError)
      else setError(errorMessage(conversionError))
    } finally { setSaving(false) }
  }
  const createLocalBlock = async () => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try {
      const record = await client.addPlacement(scope, selected.id, {
        operation: 'create_block',
        block_kind: newBlockKind,
        block_name: newBlockName.trim(),
        markdown: newBlockMarkdown,
        position: newBlockPosition,
        library_visible: newBlockLibraryVisible,
        audience_profile: placementAudience,
      })
      applyCompositionRecord(record, `${blockKinds.find((item) => item.value === newBlockKind)?.label ?? 'Content'} added.`)
      setNewBlockOpen(false); setInserterOpen(false); setNewBlockKind('rich_text'); setNewBlockName(''); setNewBlockMarkdown(''); setNewBlockPosition(null); setNewBlockLibraryVisible(false); setPlacementAudience('shared')
    } catch (blockError) { setError(errorMessage(blockError)) } finally { setSaving(false) }
  }
  const openInserter = (position: number | null) => {
    setNewBlockPosition(position); setNewBlockOpen(false); setInserterOpen(true); setActivePanel(null)
    setNewBlockKind('rich_text'); setNewBlockName(''); setNewBlockMarkdown(''); setNewBlockLibraryVisible(false); setPlacementAudience('shared')
  }
  const closeInsertion = () => {
    restoreInsertionPosition.current = newBlockPosition
    setInserterOpen(false); setNewBlockOpen(false); setNewBlockPosition(null)
  }
  const chooseContentPreset = (preset: (typeof contentPresets)[number]) => {
    setNewBlockKind(preset.kind); setNewBlockName(preset.label); setNewBlockMarkdown(preset.markdown); setNewBlockOpen(true); setInserterOpen(false)
    setEditorGeneration((value) => value + 1)
  }
  const beginBlockEdit = (placement: DocumentPlacement) => {
    setEditingBlock({ placement, draft: placement.resolved_markdown })
    setReuseReview(null); setError(null); setMessage(null)
  }
  const saveBlockEdit = async () => {
    if (!selected || selected === 'new' || !editingBlock) return
    setSaving(true); setError(null)
    try {
      const impact = await client.getReuseImpact(scope, selected.id, editingBlock.placement.id)
      if (impact.live_audience_count > 1) {
        setReuseReview({ placementId: editingBlock.placement.id, impact, draft: editingBlock.draft })
        setEditingBlock(null)
        setMessage('Review the affected audiences before saving this shared content.')
        return
      }
      const record = await client.updateSharedBlock(
        scope,
        selected.id,
        editingBlock.placement.id,
        editingBlock.draft,
        editingBlock.placement.resolved_revision_id,
      )
      applyCompositionRecord(record, 'Content saved.')
      setEditingBlock(null)
    } catch (blockError) {
      if (blockError instanceof RevisionConflictError) setConflict(blockError)
      else setError(errorMessage(blockError))
    } finally { setSaving(false) }
  }
  const addPlacement = async () => {
    if (!selected || selected === 'new' || !sourceDocumentId) return
    const source = results.find((item) => item.id === sourceDocumentId)
    if (!source) return
    setSaving(true); setError(null)
    try {
      const record = await client.addPlacement(scope, selected.id, {
        source_document_id: source.id,
        resolution_mode: placementMode,
        pinned_revision_id: placementMode === 'pinned' ? source.current_revision_id : null,
        position: newBlockPosition,
        audience_profile: placementAudience,
      })
      applyCompositionRecord(record, `${source.title} inserted.`); setSourceDocumentId(''); setActivePanel(null); setNewBlockPosition(null)
    } catch (placementError) { setError(errorMessage(placementError)) } finally { setSaving(false) }
  }
  const reuseLibraryBlock = async (block: BlockLibraryItem) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try {
      const record = await client.addPlacement(scope, selected.id, {
        operation: 'reuse_block',
        source_block_id: block.id,
        resolution_mode: placementMode,
        pinned_revision_id: placementMode === 'pinned' ? block.revision_id : null,
        position: newBlockPosition,
        audience_profile: placementAudience,
      })
      applyCompositionRecord(record, `${block.name} added as a ${placementMode} block.`)
      setBlockLibraryQuery(''); setActivePanel(null); setInserterOpen(false); setNewBlockPosition(null)
    } catch (placementError) { setError(errorMessage(placementError)) } finally { setSaving(false) }
  }
  const changePlacementMode = async (placementId: string, mode: 'live' | 'pinned', revisionId: string) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try {
      const record = await client.updatePlacement(scope, selected.id, placementId, { resolution_mode: mode, pinned_revision_id: mode === 'pinned' ? revisionId : null })
      applyCompositionRecord(record, mode === 'live' ? 'Content now follows source updates.' : 'This version is now retained.')
    } catch (placementError) { setError(errorMessage(placementError)) } finally { setSaving(false) }
  }
  const changePlacementAudience = async (placementId: string, audience: PlacementAudienceProfile) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try {
      const record = await client.updatePlacement(scope, selected.id, placementId, { audience_profile: audience })
      applyCompositionRecord(record, translate('documentation.audienceUpdated'))
    } catch (placementError) { setError(errorMessage(placementError)) } finally { setSaving(false) }
  }
  const removePlacement = async (placementId: string) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try { applyCompositionRecord(await client.removePlacement(scope, selected.id, placementId), 'Content removed from the document.') }
    catch (placementError) { setError(errorMessage(placementError)) } finally { setSaving(false) }
  }
  const reviewPlacement = async (placementId: string) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try {
      const impact = await client.getReuseImpact(scope, selected.id, placementId)
      setReuseReview({ placementId, impact, draft: impact.markdown })
    } catch (reviewError) { setError(errorMessage(reviewError)) } finally { setSaving(false) }
  }
  const saveSharedBlock = async () => {
    if (!selected || selected === 'new' || !reuseReview) return
    setSaving(true); setError(null)
    try {
      const record = await client.updateSharedBlock(scope, selected.id, reuseReview.placementId, reuseReview.draft, reuseReview.impact.revision_id)
      applyCompositionRecord(record, `Shared block updated across ${reuseReview.impact.live_audience_count} live audience${reuseReview.impact.live_audience_count === 1 ? '' : 's'}.`)
      if (record.block_id === reuseReview.impact.block_id) { setMarkdown(record.markdown); setEditorGeneration((value) => value + 1) }
      setReuseReview(null)
    } catch (reviewError) {
      if (reviewError instanceof RevisionConflictError) setConflict(reviewError)
      else setError(errorMessage(reviewError))
    } finally { setSaving(false) }
  }
  const detachPlacement = async () => {
    if (!selected || selected === 'new' || !reuseReview) return
    setSaving(true); setError(null)
    try {
      applyCompositionRecord(await client.detachPlacement(scope, selected.id, reuseReview.placementId), 'An independent copy was created in this workspace.')
      setReuseReview(null)
    } catch (detachError) { setError(errorMessage(detachError)) } finally { setSaving(false) }
  }
  const loadKeys = async () => {
    if (!selected || selected === 'new') return
    const [bindings, report] = await Promise.all([
      client.listKeyBindings(scope, selected.id),
      client.listDocumentKeys(scope, selected.id),
    ])
    setKeyBindings([...bindings.results]); setKeyReport(report); setAddressableTypes([...bindings.addressable_entity_types])
  }
  // The server enforces this grammar and refuses anything else. Checking it here means
  // a capitalised word is answered as you type instead of by a failed request.
  const bindingNameValid = /^[a-z][a-z0-9_]{0,39}$/.test(bindingName)
  const bindingTargetable = (entityType: string) => addressableTypes.length === 0 || addressableTypes.includes(entityType)
  const declareBinding = async (entity: EntityMentionOption) => {
    if (!selected || selected === 'new' || !bindingNameValid) return
    setSaving(true); setError(null)
    try {
      await client.declareKeyBinding(scope, selected.id, bindingName.trim(), entity.id)
      setBindingName(''); setMentionQuery(''); setMentionOptions([]); await loadKeys()
    } catch (bindingError) { setError(errorMessage(bindingError)) } finally { setSaving(false) }
  }
  const retireBinding = async (bindingId: string) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try { await client.archiveKeyBinding(scope, selected.id, bindingId); await loadKeys() }
    catch (bindingError) { setError(errorMessage(bindingError)) } finally { setSaving(false) }
  }
  const insertKey = (binding: DocumentKeyBinding, path: string) => {
    // A key is an autolink on the scheme the dialect already understands, so this is
    // the same insertion shape as a record reference rather than new editor syntax.
    const target = `<tekdocs://key/${binding.name}.${path}>`
    const append = (current: string) => {
      if (path === 'content') return `${current}${current && !current.endsWith('\n\n') ? (current.endsWith('\n') ? '\n' : '\n\n') : ''}${target}\n`
      return `${current}${current && !current.endsWith('\n') ? ' ' : ''}${target}`
    }
    if (editingBlock) setEditingBlock({ ...editingBlock, draft: append(editingBlock.draft) })
    else if (newBlockOpen) setNewBlockMarkdown(append(newBlockMarkdown))
    else setMarkdown(append)
    setEditorGeneration((value) => value + 1)
  }
  const insertMention = (entity: EntityMentionOption) => {
    const label = entity.display_name.replace(/[\\[\]]/g, '\\$&')
    const append = (current: string) => `${current}${current && !current.endsWith('\n') ? '\n\n' : ''}[${label}](tekdocs://entity/${entity.id})`
    if (editingBlock) setEditingBlock({ ...editingBlock, draft: append(editingBlock.draft) })
    else if (newBlockOpen) setNewBlockMarkdown(append(newBlockMarkdown))
    else if (selected !== 'new' && newBlockPosition !== null) {
      setNewBlockKind('entity_reference'); setNewBlockName(entity.display_name); setNewBlockMarkdown(append('')); setNewBlockOpen(true); setActivePanel(null)
    }
    else setMarkdown(append)
    setMentionQuery(''); setMentionOptions([]); setEditorGeneration((value) => value + 1)
  }
  const importMarkdown = async (file: File) => {
    setSaving(true); setError(null)
    try {
      const imported = await client.importMarkdown(scope, file, file.name.replace(/\.md$/i, '') || 'Imported document', 'general', false)
      open(imported); setMessage('Markdown imported as a new document.'); setRevision((value) => value + 1)
    } catch (importError) { setError(errorMessage(importError)) } finally { setSaving(false); if (importInput.current) importInput.current.value = '' }
  }
  const instantiateSelectedTemplate = async () => {
    if (!selected || selected === 'new' || !selected.is_template) return
    setSaving(true); setError(null)
    try {
      const created = await client.instantiateTemplate(scope, selected.id, `New from ${selected.title}`, selected.category)
      open(created); setMessage('Independent document created from the template.'); setRevision((value) => value + 1)
    } catch (templateError) { setError(errorMessage(templateError)) } finally { setSaving(false) }
  }
  const instantiateClientTemplate = async () => {
    if (!templateDraft) return
    setSaving(true); setError(null)
    try {
      const created = await client.instantiateTemplate(
        scope,
        templateDraft.source.id,
        templateDraft.title.trim(),
        templateDraft.source.category,
        templateDraft.rules,
      )
      setTemplateDraft(null); open(created); setMessage('Client document created from a retained template revision.'); setRevision((value) => value + 1)
    } catch (templateError) { setError(errorMessage(templateError)) } finally { setSaving(false) }
  }
  const previewSelectedTemplateRollout = async () => {
    if (!selected || selected === 'new' || !selected.template_enrollment_id) return
    setSaving(true); setError(null)
    try { setTemplateRollout(await client.previewTemplateRollout(scope, selected.template_enrollment_id)) }
    catch (templateError) { setError(errorMessage(templateError)) } finally { setSaving(false) }
  }
  const applySelectedTemplateRollout = async () => {
    if (!selected || selected === 'new' || !templateRollout || templateRollout.conflicts.length > 0) return
    setSaving(true); setError(null)
    try {
      const applied = await client.applyTemplateRollout(
        scope,
        templateRollout.enrollment_id,
        templateRollout.applied_revision_id,
        Object.fromEntries(templateRollout.added.map((item) => [item.source_block_id, 'copy' as const])),
      )
      setTemplateRollout(applied); setMessage(`Template revision ${applied.available_revision} applied.`); setRevision((value) => value + 1)
    } catch (templateError) { setError(errorMessage(templateError)) } finally { setSaving(false) }
  }
  const openRemoteSource = async () => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try {
      const [source, observations] = await Promise.all([client.getRemoteSource(scope, selected.id), client.listRemoteObservations(scope, selected.id).catch(() => ({ results: [], count: 0 }))])
      setRemoteSource(source ?? null)
      if (source) setRemoteSourceDraft({ url: source.url, source_kind: source.source_kind, enabled: source.enabled, check_interval_minutes: source.check_interval_minutes })
      setRemoteObservations(observations.results); setRemoteSourceOpen(true)
    } catch (sourceError) { setError(errorMessage(sourceError)) } finally { setSaving(false) }
  }
  const saveRemoteSource = async () => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try { setRemoteSource(await client.saveRemoteSource(scope, selected.id, remoteSourceDraft)); setMessage('Remote source saved.') }
    catch (sourceError) { setError(errorMessage(sourceError)) } finally { setSaving(false) }
  }
  const checkRemoteSource = async () => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try { const observation = await client.checkRemoteSource(scope, selected.id); setRemoteObservations((items) => [observation, ...items]); setMessage(observation.state === 'changed' ? 'A source change is ready for review.' : 'Remote source checked.') }
    catch (sourceError) { setError(errorMessage(sourceError)) } finally { setSaving(false) }
  }
  const applyRemoteObservation = async (observation: DocumentRemoteObservation) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try { await client.applyRemoteObservation(scope, selected.id, observation.id); setMessage('Reviewed source change applied as a new revision.'); setRevision((value) => value + 1); setRemoteSourceOpen(false) }
    catch (sourceError) { setError(errorMessage(sourceError)) } finally { setSaving(false) }
  }
  const uploadAttachment = async (file: File) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try {
      const attachment = await client.uploadAttachment(scope, selected.id, file)
      setSelected({ ...selected, attachments: [...selected.attachments, attachment], attachment_count: selected.attachment_count + 1 })
      setMessage(`${attachment.filename} attached.`)
    } catch (attachmentError) { setError(errorMessage(attachmentError)) } finally { setSaving(false); if (attachmentInput.current) attachmentInput.current.value = '' }
  }
  const replacePrimaryFile = async (file: File) => {
    if (!selected || selected === 'new' || !selected.primary_file) return
    setSaving(true); setError(null)
    try {
      const replacement = await client.replacePrimaryFile(scope, selected.id, file)
      const prior = selected.primary_file_versions.map((item) => ({ ...item, is_current: false }))
      setSelected({ ...selected, primary_file: replacement, primary_file_versions: [replacement, ...prior] })
      setViewedPdf(replacement.media_type === 'application/pdf' ? { filename: replacement.filename, url: client.attachmentDownloadUrl(scope, selected.id, replacement.id) } : null)
      setMessage(`${replacement.filename} saved as primary file version ${replacement.version_number}.`)
      setRevision((value) => value + 1)
    } catch (replacementError) { setError(errorMessage(replacementError)) } finally { setSaving(false); if (replacementFileInput.current) replacementFileInput.current.value = '' }
  }
  const removeAttachment = async (attachmentId: string) => {
    if (!selected || selected === 'new') return
    setSaving(true); setError(null)
    try {
      await client.archiveAttachment(scope, selected.id, attachmentId)
      setSelected({ ...selected, attachments: selected.attachments.filter((item) => item.id !== attachmentId), attachment_count: selected.attachment_count - 1 })
      setMessage('Attachment removed from the document.')
    } catch (attachmentError) { setError(errorMessage(attachmentError)) } finally { setSaving(false) }
  }
  const insertAttachment = (attachmentId: string, filename: string) => {
    const label = filename.replaceAll('[', '\\[').replaceAll(']', '\\]')
    const append = (current: string) => `${current}${current && !current.endsWith('\n') ? '\n\n' : ''}[${label}](tekdocs://attachment/${attachmentId})`
    if (editingBlock) setEditingBlock({ ...editingBlock, draft: append(editingBlock.draft) })
    else if (newBlockOpen) setNewBlockMarkdown(append(newBlockMarkdown))
    else if (selected !== 'new' && newBlockPosition !== null) {
      setNewBlockKind('file_reference'); setNewBlockName(filename); setNewBlockMarkdown(append('')); setNewBlockOpen(true); setActivePanel(null)
    }
    else setMarkdown(append)
    setEditorGeneration((value) => value + 1)
  }
  const loadPublicationPreflight = async (source: DocumentRecord, audience: PublicationAudience) => {
    if (!client.preflight) { setPublicationPreflight({ phase: 'error' }); return }
    setPublicationPreflight({ phase: 'loading' })
    try { setPublicationPreflight({ phase: 'ready', report: await client.preflight(scope, source.id, audience) }) }
    catch { setPublicationPreflight({ phase: 'error' }) }
  }
  const beginPublication = (source: DocumentRecord, supersedes: DocumentPublication | null = null) => {
    setPublicationControl(null)
    const audience = supersedes?.audience ?? 'msp_internal'
    setPublicationForm({ source, reason: '', audience, retention: 'permanent', reviewOn: '', supersedesId: supersedes?.id ?? null })
    void loadPublicationPreflight(source, audience)
  }
  const changeTopic = async (nextTopic: DocumentTopicType) => {
    if (!selected || selected === 'new' || nextTopic === selected.topic_type) { setTopicType(nextTopic); return }
    if (!client.convertTopic) { setError(translate('documentation.topicConversionUnavailable')); return }
    setSaving(true); setError(null)
    try {
      const preview = await client.convertTopic(scope, selected.id, nextTopic, selected.current_revision_id, false)
      if (!('converted_markdown' in preview)) return
      const label = topicTypes.find((item) => item.value === nextTopic)?.label ?? nextTopic
      if (!window.confirm(translate('documentation.topicConversionConfirm', { title: selected.title, type: label }))) return
      const result = await client.convertTopic(scope, selected.id, nextTopic, selected.current_revision_id, true)
      if ('id' in result) { setSelected(result); setTopicType(result.topic_type ?? 'unstructured'); setMarkdown(result.markdown); setMessage(translate('documentation.topicConverted', { type: label })); setRevision((value) => value + 1) }
    } catch (conversionError) { setError(errorMessage(conversionError)) } finally { setSaving(false) }
  }
  const runDocumentCheck = async () => {
    if (!selected || selected === 'new' || !client.preflight) return
    setDocumentCheck({ phase: 'loading' })
    try { setDocumentCheck({ phase: 'ready', report: await client.preflight(scope, selected.id, 'msp_internal') }) }
    catch { setDocumentCheck({ phase: 'error' }) }
  }
  const publishStatic = async () => {
    if (!publicationForm || !publicationForm.reason.trim()) return
    if (!window.confirm(`Publish an immutable STATIC version of “${publicationForm.source.title}”? Its retained artifacts and lifecycle record cannot be edited or deleted.`)) return
    setSaving(true); setError(null)
    try {
      const publication = await client.publish(scope, publicationForm.source.id, {
        reason: publicationForm.reason.trim(), audience: publicationForm.audience, retention: publicationForm.retention,
        retention_review_on: publicationForm.retention === 'review_on' ? publicationForm.reviewOn : null,
        supersedes_id: publicationForm.supersedesId,
      })
      const sourceId = publicationForm.source.id
      setLoaded((current) => current ? { ...current, results: current.results.map((document) => document.id === sourceId ? { ...document, publications: [publication, ...document.publications], publication_count: document.publication_count + 1 } : document) } : current)
      setSelected(null); setPublicationForm(null)
      setPublicationView({ sourceId, phase: 'ready', record: publication })
      setMessage(publication.lifecycle_state === 'pending_approval' ? 'STATIC snapshot submitted. A different authorized user must approve client portal availability.' : publication.supersedes_id ? 'Corrected STATIC publication created; the prior version remains retained.' : 'Immutable STATIC publication and retained artifacts created.')
    } catch (publicationError) { setError(errorMessage(publicationError)) } finally { setSaving(false) }
  }
  const applyPublicationControl = async () => {
    if (!publicationView?.record || !publicationControl?.reason.trim()) return
    const verb = publicationControl.action === 'approve' ? 'Approve' : 'Withdraw'
    if (!window.confirm(`${verb} “${publicationView.record.title}”? This decision is retained in its append-only publication history.`)) return
    setSaving(true); setError(null)
    try {
      const record = publicationControl.action === 'approve'
        ? await client.approvePublication(scope, publicationView.sourceId, publicationView.record.id, publicationControl.reason.trim())
        : await client.withdrawPublication(scope, publicationView.sourceId, publicationView.record.id, publicationControl.reason.trim())
      setPublicationView({ sourceId: publicationView.sourceId, phase: 'ready', record })
      setPublicationControl(null)
      setRevision((value) => value + 1)
      setMessage(publicationControl.action === 'approve' ? 'Publication approved for its intended audience.' : 'Publication withdrawn from audience availability; retained evidence remains accessible to authorized MSP staff.')
    } catch (controlError) { setError(errorMessage(controlError)) } finally { setSaving(false) }
  }

  const insertionPoint = (position: number) => {
    const isCurrent = newBlockPosition === position
    return <div className={`document-insertion${isCurrent ? ' active' : ''}`}>
      {!isCurrent && <button className="document-insert-button" type="button" aria-label="Add content here" data-insertion-position={position} onClick={() => openInserter(position)}><Plus size={18} /></button>}
      {isCurrent && inserterOpen && <div ref={insertionMenu} className="document-insert-menu" role="group" aria-label="Add content" onKeyDown={(event) => { if (event.key === 'Escape') { event.preventDefault(); closeInsertion() } }}>
        <div className="document-insert-menu-heading"><strong>Add content</strong><button className="icon-button" type="button" aria-label="Close add content menu" onClick={closeInsertion}><X size={16} /></button></div>
        <div className="document-insert-types">{contentPresets.map((preset) => { const Icon = preset.icon; return <button key={preset.label} type="button" onClick={() => chooseContentPreset(preset)}><Icon size={17} /><span>{preset.label}</span></button> })}</div>
        <div className="document-insert-secondary"><button type="button" onClick={() => { setInserterOpen(false); setActivePanel('reuse') }}><Copy size={16} />{translate('documentation.existingContent')}</button><button type="button" onClick={() => { setInserterOpen(false); setActivePanel('files') }}><Paperclip size={16} />{translate('documentation.file')}</button><button type="button" onClick={() => { setInserterOpen(false); setActivePanel('reuse') }}><Link2 size={16} />{translate('documentation.tekdocsRecord')}</button></div>
      </div>}
      {isCurrent && newBlockOpen && selected && selected !== 'new' && <div className="document-inline-editor">
        <div className="document-inline-editor-heading"><strong>{newBlockName || 'New content'}</strong><button className="icon-button" type="button" aria-label="Cancel adding content" onClick={closeInsertion}><X size={16} /></button></div>
        <Suspense fallback={<p role="status">Loading editor…</p>}><Editor key={`new-content-${newBlockKind}-${editorGeneration}`} initialMarkdown={newBlockMarkdown} title={newBlockName || 'New content'} description="" organizationId={workspace?.id} documentId={selected.id} onMarkdownChange={setNewBlockMarkdown} /></Suspense>
        <label className="placement-audience-field">{translate('documentation.audienceLabel')}<select value={placementAudience} onChange={(event) => setPlacementAudience(event.target.value as PlacementAudienceProfile)}><option value="shared">{translate('documentation.audienceShared')}</option><option value="msp_internal">{translate('documentation.audienceMspInternal')}</option><option value="client_visible">{translate('documentation.audienceClientVisible')}</option></select></label>
        {!workspace && <label className="checkbox-field"><input type="checkbox" checked={newBlockLibraryVisible} onChange={(event) => setNewBlockLibraryVisible(event.target.checked)} />Make this content available for reuse in client documents</label>}
        <div className="document-actions"><button className="primary-button" type="button" disabled={saving} onClick={() => { void createLocalBlock() }}>{saving ? 'Adding…' : 'Add'}</button><button className="secondary-button" type="button" disabled={saving} onClick={closeInsertion}>{translate('common.cancel')}</button></div>
      </div>}
    </div>
  }

  const exportableFiles = selected && selected !== 'new'
    ? [...selected.primary_file_versions, ...selected.attachments]
    : []
  const displayedPlacements = selected && selected !== 'new'
    ? selected.placements.filter((placement) => audiencePreview === 'all' || placement.audience_profile === 'shared' || placement.audience_profile === audiencePreview)
    : []
  const toggleExportFile = (attachmentId: string) => {
    setExportAttachmentIds((current) => current.includes(attachmentId)
      ? current.filter((id) => id !== attachmentId)
      : [...current, attachmentId])
  }
  const activeDocumentFilterCount = [categoryFilter, collectionFilter, tagFilter, healthFilter, templateFilter === 'all' ? '' : templateFilter].filter(Boolean).length
  const documentFilterGroups: FilterMenuGroup[] = [
    {
      kind: 'choices' as const,
      label: translate('documentation.category'),
      value: categoryFilter,
      choices: [{ value: '', label: translate('documentation.allCategories') }, ...categories],
      onChange: (value) => setCategoryFilter(value as DocumentCategory | ''),
    },
    {
      kind: 'choices' as const,
      label: translate('documentation.collection'),
      value: collectionFilter,
      choices: [{ value: '', label: translate('documentation.allCollections') }, ...(loaded?.collections ?? []).map((item) => ({ value: item.value, label: `${item.value} (${item.count})` }))],
      onChange: setCollectionFilter,
    },
    {
      kind: 'choices' as const,
      label: translate('documentation.tag'),
      value: tagFilter,
      choices: [{ value: '', label: translate('documentation.allTags') }, ...(loaded?.tags ?? []).map((item) => ({ value: item.value, label: `${item.value} (${item.count})` }))],
      onChange: setTagFilter,
    },
    {
      kind: 'choices' as const,
      label: translate('documentation.health'),
      value: healthFilter,
      choices: [{ value: '', label: translate('documentation.allHealth') }, ...(loaded?.health ?? []).map((item) => ({ value: item.value, label: `${item.value.replaceAll('_', ' ')} (${item.count})` }))],
      onChange: (value) => setHealthFilter(value as DocumentHealthStatus | ''),
    },
    {
      kind: 'choices' as const,
      label: translate('documentation.type'),
      value: templateFilter,
      choices: [
        { value: 'all', label: translate('documentation.documentsAndTemplates') },
        { value: 'documents', label: translate('documentation.documents') },
        { value: 'templates', label: translate('documentation.templates') },
      ],
      onChange: (value) => setTemplateFilter(value as typeof templateFilter),
    },
  ]
  const clearDocumentFilters = () => {
    setCategoryFilter('')
    setCollectionFilter('')
    setTagFilter('')
    setHealthFilter('')
    setTemplateFilter('all')
  }

  if (documentationView === 'maps') return <DocumentationMaps workspace={workspace} onShowDocuments={() => setDocumentationView('documents')} />

  return <>
    <nav className="segmented-control documentation-mode" aria-label="Documentation view"><button type="button" aria-pressed="true">{translate('documentation.documents')}</button><button type="button" aria-pressed="false" onClick={() => setDocumentationView('maps')}>{translate('documentation.maps')}</button></nav>
    <header className="page-header"><div><h1>Documentation</h1></div><div className="page-actions"><button className="secondary-button" type="button" aria-pressed={indexMode === 'health'} onClick={() => setIndexMode((value) => value === 'browse' ? 'health' : 'browse')}><CalendarCheck2 size={16} aria-hidden="true" /><span className="button-label">{indexMode === 'health' ? translate('documentation.browse') : translate('documentation.contentHealth')}</span></button><input ref={importInput} aria-label="Markdown file to import" className="sr-only" type="file" accept=".md,text/markdown" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importMarkdown(file) }} /><button className="secondary-button" type="button" aria-label={translate('documentation.import')} title={translate('documentation.import')} disabled={saving} onClick={() => importInput.current?.click()}><FileUp size={16} aria-hidden="true" /><span className="button-label">{translate('documentation.import')}</span></button><button className="primary-button" type="button" aria-label={translate('documentation.new')} title={translate('documentation.new')} onClick={create}><Plus size={16} aria-hidden="true" /><span className="button-label">{translate('documentation.new')}</span></button></div></header>
    {error && <div className="form-message error" role="alert">{error}</div>}
    {message && <div className="form-message success" role="status">{message}</div>}
    <section className="content-section document-index" aria-labelledby="document-index-heading">
      <div className="section-heading"><h2 id="document-index-heading">{indexMode === 'health' ? translate('documentation.contentHealth') : translate('documentation.documents')}</h2><span>{phase === 'ready' ? translate('documentation.resultCount', { count: results.length }) : translate('common.loading')}</span></div>
      <div className="document-filters"><label className="document-search-field"><span>{translate('documentation.search')}</span><input type="search" value={documentQuery} onChange={(event) => setDocumentQuery(event.target.value)} /></label><FilterMenu groups={documentFilterGroups} activeCount={activeDocumentFilterCount} onClear={clearDocumentFilters} menuLabel={translate('documentation.filterMenu')} /></div>
      {visiblePhase === 'loading' && <p className="empty-state" role="status">Loading documents…</p>}
      {visiblePhase === 'error' && <p className="empty-state">Documents are unavailable.</p>}
      {visiblePhase === 'ready' && results.length === 0 && <p className="empty-state">No documents have been added to this workspace.</p>}
      {visiblePhase === 'ready' && indexMode === 'health' && results.length > 0 && results.every((document) => document.health_status === 'current') && <p className="empty-state">{translate('documentation.healthEmpty')}</p>}
      {visiblePhase === 'ready' && results.length > 0 && <ul className="document-title-list">{results.filter((document) => indexMode === 'browse' || document.health_status !== 'current').map((document) => <li key={document.id}><button type="button" onClick={() => open(document)}><BookOpenText size={17} /><span><strong>{document.title || translate('documentation.untitled')}</strong><small>{[document.collection, categories.find((item) => item.value === document.category)?.label, document.health_status?.replaceAll('_', ' '), document.owner_name].filter(Boolean).join(' · ')}</small>{document.matching_excerpt && <span className="document-search-excerpt">{document.matching_excerpt}</span>}{(document.tags ?? []).length > 0 && <span className="document-tag-list">{document.tags!.join(' · ')}</span>}</span></button>{document.publications.length > 0 && <ul className="static-publication-list">{document.publications.map((publication) => <li key={publication.id}><button type="button" onClick={() => { void openPublication(document, publication) }}><FileCheck2 size={15} /><span><strong>{publication.title}</strong><small>STATIC · {publication.lifecycle_state.replace('_', ' ')} · {publication.audience.replace('_', ' ')} · {new Date(publication.published_at).toLocaleString()}</small></span></button></li>)}</ul>}</li>)}</ul>}
    </section>
    {workspace && templateLibrary.length > 0 && <section className="content-section client-template-library" aria-labelledby="client-template-library-heading">
      <div className="section-heading"><div><h2 id="client-template-library-heading">MSP client templates</h2><p>Start a client-owned document from an explicitly published, versioned MSP template.</p></div><span>{templateLibrary.length} available</span></div>
      <ul>{templateLibrary.map((template) => <li key={template.id}><span><strong>{template.title}</strong><small>{template.placement_count} section{template.placement_count === 1 ? '' : 's'} · {categories.find((item) => item.value === template.category)?.label}</small></span><button className="secondary-button" type="button" onClick={() => setTemplateDraft({ source: template, title: `${workspace.name} — ${template.title}`, rules: Object.fromEntries(template.placements.slice(1).map((placement) => [placement.block_id, 'copy'])) })}><Copy size={15} />{translate('documentation.useTemplate')}</button></li>)}</ul>
      {templateDraft && <section className="template-draft" aria-labelledby="template-draft-heading"><div className="section-heading"><div><h3 id="template-draft-heading">Create from {templateDraft.source.title}</h3><p>The opening section is always copied. Choose how each additional section should behave.</p></div><button className="icon-button" type="button" aria-label="Cancel template" onClick={() => setTemplateDraft(null)}><X size={16} /></button></div><label>Client document title<input maxLength={240} value={templateDraft.title} onChange={(event) => setTemplateDraft({ ...templateDraft, title: event.target.value })} /></label>{templateDraft.source.placements.slice(1).map((placement) => <label key={placement.id}>{placement.block_name.replace(/ — content$/, '')}<select value={templateDraft.rules[placement.block_id] ?? 'copy'} onChange={(event) => setTemplateDraft({ ...templateDraft, rules: { ...templateDraft.rules, [placement.block_id]: event.target.value as TemplatePlacementMode } })}><option value="copy">Independent copy</option><option value="live">Live reference</option><option value="pinned">Pinned reference</option></select></label>)}<div className="document-actions"><button className="primary-button" type="button" disabled={saving || !templateDraft.title.trim()} onClick={() => { void instantiateClientTemplate() }}>{saving ? 'Creating…' : 'Create client document'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setTemplateDraft(null)}>{translate('common.cancel')}</button></div></section>}
    </section>}
    {publicationView && <section className="document-workspace static-publication" aria-label="STATIC publication">
      <div className="document-edit-heading"><div><h2>{publicationView.record?.title ?? 'STATIC publication'}</h2><p>Immutable retained version</p></div><button className="icon-button" type="button" aria-label="Close publication" onClick={close}><X size={19} /></button></div>
      {publicationView.phase === 'loading' && <p className="empty-state" role="status">Loading STATIC publication…</p>}
      {publicationView.phase === 'error' && <p className="empty-state">This STATIC publication is unavailable.</p>}
      {publicationView.phase === 'ready' && publicationView.record && <>
        <dl className="publication-lifecycle">
          <div><dt>Status</dt><dd>{publicationView.record.lifecycle_state.replace('_', ' ')}</dd></div>
          <div><dt>Audience</dt><dd>{publicationView.record.audience.replace('_', ' ')}</dd></div>
          <div><dt>Reason</dt><dd>{publicationView.record.reason}</dd></div>
          <div><dt>Retention</dt><dd>{publicationView.record.retention === 'permanent' ? 'Permanent' : `Review on ${publicationView.record.retention_review_on}`}</dd></div>
        </dl>
        <section className="publication-audiences" aria-labelledby="publication-audiences-heading"><h3 id="publication-audiences-heading">Audience availability</h3><dl>{publicationView.record.audience_projections.map((projection) => <div key={projection.audience}><dt>{projection.audience === 'msp_staff' ? 'MSP staff' : 'Client portal'}</dt><dd>{projection.available ? 'Available' : projection.state.replaceAll('_', ' ')}</dd></div>)}</dl></section>
        <div className="publication-integrity"><ShieldCheck size={18} /><div><strong>{publicationView.record.verification.valid ? 'Signature verified' : 'Verification failed'}</strong><span>{publicationView.record.signature_algorithm} · snapshot created {new Date(publicationView.record.published_at).toLocaleString()} by {publicationView.record.published_by ?? 'System'}</span><code>SHA-256 {publicationView.record.content_digest}</code><code>Key {publicationView.record.key_fingerprint}</code></div></div>
        <SanitizedMarkdown html={publicationView.record.sanitized_html} />
        <div className="document-actions">
          <a className="secondary-button" href={client.publicationExportUrl(scope, publicationView.sourceId, publicationView.record.id, 'md')}><Download size={15} />Download Markdown</a>
          <a className="secondary-button" href={client.publicationExportUrl(scope, publicationView.sourceId, publicationView.record.id, 'html')}><Download size={15} />Download HTML</a>
          <a className="secondary-button" href={client.publicationExportUrl(scope, publicationView.sourceId, publicationView.record.id, 'pdf')}><Download size={15} />Download PDF</a>
          <a className="secondary-button" href={client.publicationExportUrl(scope, publicationView.sourceId, publicationView.record.id, 'docx')} title="Compatible with Microsoft Word and Google Docs"><Download size={15} />Download DOCX</a>
          <a className="secondary-button" href={client.publicationManifestUrl(scope, publicationView.sourceId, publicationView.record.id)}><Download size={15} />Download manifest</a>
          {['published', 'review_due', 'withdrawn'].includes(publicationView.record.lifecycle_state) && !publicationView.record.superseded_by_id && results.find((document) => document.id === publicationView.sourceId) && <button className="secondary-button" type="button" onClick={() => beginPublication(results.find((document) => document.id === publicationView.sourceId)!, publicationView.record)}><FileCheck2 size={15} />{translate('documentation.publishCorrection')}</button>}
          {publicationView.record.lifecycle_state === 'pending_approval' && <button className="secondary-button" type="button" onClick={() => setPublicationControl({ action: 'approve', reason: '' })}>{translate('documentation.approvePublication')}</button>}
          {['pending_approval', 'published', 'review_due'].includes(publicationView.record.lifecycle_state) && <button className="danger-button" type="button" onClick={() => setPublicationControl({ action: 'withdraw', reason: '' })}>{translate('documentation.withdrawPublication')}</button>}
        </div>
        {publicationControl && <section className="publication-control" aria-labelledby="publication-control-heading"><h3 id="publication-control-heading">{publicationControl.action === 'approve' ? 'Approval decision' : 'Withdrawal decision'}</h3><p>{publicationControl.action === 'approve' ? 'Client-visible approval must come from a different authorized user than the snapshot publisher.' : 'Withdrawal removes audience availability without deleting the signed snapshot or retained artifacts.'}</p><label>Decision reason<textarea required maxLength={500} value={publicationControl.reason} onChange={(event) => setPublicationControl({ ...publicationControl, reason: event.target.value })} /></label><div className="document-actions"><button className={publicationControl.action === 'approve' ? 'primary-button' : 'danger-button'} type="button" disabled={saving || !publicationControl.reason.trim()} onClick={() => { void applyPublicationControl() }}>{saving ? 'Saving decision…' : publicationControl.action === 'approve' ? 'Record approval' : 'Record withdrawal'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setPublicationControl(null)}>{translate('common.cancel')}</button></div></section>}
        <section className="publication-history" aria-labelledby="publication-history-heading"><h3 id="publication-history-heading">Publication history</h3><ol>{publicationView.record.control_events.map((event) => <li key={event.id}><strong>{event.action.replace('_', ' ')}</strong><span>{event.reason}</span><small>{event.actor ?? 'System'} · {new Date(event.occurred_at).toLocaleString()}</small></li>)}</ol></section>
        {publicationView.record.artifacts.some((artifact) => artifact.kind === 'attachment') && <section className="publication-artifacts" aria-labelledby="retained-artifacts-heading"><h3 id="retained-artifacts-heading">Retained attachments</h3><ul>{publicationView.record.artifacts.filter((artifact) => artifact.kind === 'attachment').map((artifact) => <li key={artifact.id}><a href={client.publicationArtifactUrl(scope, publicationView.sourceId, publicationView.record!.id, artifact.id)}><strong>{artifact.filename}</strong><small>{artifact.media_type} · {artifact.size.toLocaleString()} bytes · {artifact.checksum.slice(0, 12)}</small></a></li>)}</ul></section>}
      </>}
    </section>}
    {publicationForm && <section className="publication-form" aria-labelledby="publication-form-heading">
      <div className="section-heading"><div><h2 id="publication-form-heading">{publicationForm.supersedesId ? 'Publish correction' : 'Publish STATIC'}</h2><p>{publicationForm.source.title}</p></div><button className="icon-button" type="button" aria-label="Cancel publication" onClick={() => setPublicationForm(null)}><X size={18} /></button></div>
      <section className="publication-preflight" aria-labelledby="publication-preflight-heading">
        <h3 id="publication-preflight-heading">{translate('documentation.publicationCheck')}</h3>
        {publicationPreflight?.phase === 'loading' && <p role="status">{translate('documentation.publicationChecking')}</p>}
        {publicationPreflight?.phase === 'error' && <p role="alert">{translate('documentation.publicationCheckUnavailable')}</p>}
        {publicationPreflight?.phase === 'ready' && publicationPreflight.report && <><p>{publicationPreflight.report.valid ? translate('documentation.readyToPublish') : translate('documentation.publicationBlockers', { count: publicationPreflight.report.counts.blocker })}{publicationPreflight.report.counts.warning > 0 ? ` ${translate('documentation.publicationWarnings', { count: publicationPreflight.report.counts.warning })}` : ''}</p>{publicationPreflight.report.findings.length > 0 && <ul>{publicationPreflight.report.findings.map((finding, index) => <li key={`${finding.code}-${finding.section_id ?? ''}-${index}`}><strong>{finding.severity}: {finding.summary}</strong><span>{finding.remediation}</span></li>)}</ul>}</>}
      </section>
      <label>Publication reason<textarea required maxLength={500} value={publicationForm.reason} onChange={(event) => setPublicationForm({ ...publicationForm, reason: event.target.value })} /></label>
      <div className="publication-form-fields"><label>Audience<select disabled={publicationForm.supersedesId !== null} value={publicationForm.audience} onChange={(event) => { const audience = event.target.value as PublicationAudience; setPublicationForm({ ...publicationForm, audience }); void loadPublicationPreflight(publicationForm.source, audience) }}><option value="msp_internal">MSP internal</option>{workspace && <option value="client_visible">Client visible</option>}</select></label><label>Retention<select value={publicationForm.retention} onChange={(event) => setPublicationForm({ ...publicationForm, retention: event.target.value as PublicationRetention, reviewOn: event.target.value === 'permanent' ? '' : publicationForm.reviewOn })}><option value="permanent">Permanent</option><option value="review_on">Review on date</option></select></label>{publicationForm.retention === 'review_on' && <label>Review date<input type="date" required value={publicationForm.reviewOn} onChange={(event) => setPublicationForm({ ...publicationForm, reviewOn: event.target.value })} /></label>}</div>
      <p>Publishing retains signed Markdown, HTML, PDF, manifest, and referenced attachment bytes. Client-visible snapshots remain pending until a different authorized user approves them.</p>
      <div className="document-actions"><button className="primary-button" type="button" disabled={saving || publicationPreflight?.phase !== 'ready' || !publicationPreflight.report?.valid || !publicationForm.reason.trim() || (publicationForm.retention === 'review_on' && !publicationForm.reviewOn)} onClick={() => { void publishStatic() }}>{saving ? 'Publishing…' : publicationForm.supersedesId ? 'Publish correction' : 'Publish immutable version'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setPublicationForm(null)}>{translate('common.cancel')}</button></div>
    </section>}
    {selected && <section className="document-workspace" aria-label={selected === 'new' ? 'New document' : selected.title}>
      {selected === 'new' ? <>
        <div className="document-edit-heading"><label>Document title<input autoFocus maxLength={240} required value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>Category<select value={category} onChange={(event) => setCategory(event.target.value as DocumentCategory)}>{categories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>{newDocumentMode === 'write' && <label className="checkbox-field"><input type="checkbox" checked={isTemplate} onChange={(event) => setIsTemplate(event.target.checked)} />Reusable template</label>}<button className="icon-button" type="button" aria-label="Close document" onClick={close}><X size={19} /></button></div>
        <div className="document-actions" role="group" aria-label="Document source"><button className={newDocumentMode === 'write' ? 'secondary-button selected' : 'secondary-button'} type="button" onClick={() => { setNewDocumentMode('write'); setNewPrimaryFile(null) }}>{translate('documentation.writeDocument')}</button><button className={newDocumentMode === 'file' ? 'secondary-button selected' : 'secondary-button'} type="button" onClick={() => { setNewDocumentMode('file'); setIsTemplate(false) }}>{translate('documentation.uploadFile')}</button></div>
        {newDocumentMode === 'write' && <fieldset className="document-topic-picker"><legend>{translate('documentation.documentType')}</legend><p>{translate('documentation.documentTypeChoiceHelp')}</p><div>{topicTypes.map((topic) => <label key={topic.value}><input type="radio" name="new-document-topic" value={topic.value} checked={topicType === topic.value} onChange={() => setTopicType(topic.value)} /><span><strong>{topic.label}</strong><small>{topic.description}</small></span></label>)}</div></fieldset>}
        {newDocumentMode === 'file' && <div className="document-context-panel primary-file-picker"><label>Primary file<input ref={newPrimaryFileInput} type="file" required onChange={(event) => setNewPrimaryFile(event.target.files?.[0] ?? null)} /></label><p>The file is scanned before the document is created. PDF files can be read here; other supported files remain available for download.</p></div>}
        <Suspense fallback={<section className="content-section" role="status">Loading editor…</section>}><Editor key={`new-${newDocumentMode}-${editorGeneration}`} initialMarkdown={markdown} title={title || 'Untitled document'} description="" organizationId={workspace?.id} onMarkdownChange={setMarkdown} /></Suspense>
        <div className="document-actions"><button className="primary-button" type="button" disabled={saving || !title.trim() || (newDocumentMode === 'file' && !newPrimaryFile)} onClick={() => { if (newDocumentMode === 'file') void createFileBackedDocument(); else void save() }}>{saving ? 'Creating…' : newDocumentMode === 'file' ? 'Create file-backed document' : 'Create document'}</button><button className="secondary-button" type="button" onClick={close}>{translate('common.cancel')}</button></div>
      </> : <>
        <header className="document-reader-header"><div><strong>{selected.title}</strong><span>{categories.find((item) => item.value === selected.category)?.label ?? selected.category}{selected.is_template ? ' · Template' : ''}{selected.is_reference ? ' · MSP reference' : ''}</span></div><div className="document-reader-actions"><button className="secondary-button" type="button" disabled={saving} onClick={() => beginPublication(selected)}><FileCheck2 size={15} />{translate('documentation.publishStatic')}</button><button className={activePanel === 'files' ? 'secondary-button selected' : 'secondary-button'} type="button" onClick={() => setActivePanel(activePanel === 'files' ? null : 'files')}><Paperclip size={15} />Files{selected.attachment_count > 0 ? ` (${selected.attachment_count})` : ''}</button><button className={activePanel === 'history' ? 'secondary-button selected' : 'secondary-button'} type="button" onClick={() => { setActivePanel(activePanel === 'history' ? null : 'history'); if (activePanel !== 'history') void loadHistory() }}><History size={15} />{translate('documentation.history')}</button><button className={activePanel === 'keys' ? 'secondary-button selected' : 'secondary-button'} type="button" onClick={() => { setActivePanel(activePanel === 'keys' ? null : 'keys'); if (activePanel !== 'keys') void loadKeys() }}><Key size={15} />{translate('documentation.keys')}{keyReport && keyReport.unresolved_count > 0 ? ` (${keyReport.unresolved_count})` : ''}</button><button className={activePanel === 'export' ? 'secondary-button selected' : 'secondary-button'} type="button" onClick={() => setActivePanel(activePanel === 'export' ? null : 'export')}><Download size={15} />{translate('documentation.export')}</button><button className={activePanel === 'details' ? 'secondary-button selected' : 'secondary-button'} type="button" aria-label={translate('documentation.documentSettings')} aria-expanded={activePanel === 'details'} onClick={() => setActivePanel(activePanel === 'details' ? null : 'details')}><Settings size={15} aria-hidden="true" /><span>{translate('documentation.documentSettings')}</span></button><button className="icon-button" type="button" aria-label="Close document" onClick={close}><X size={19} /></button></div></header>

        {activePanel === 'details' && <section ref={documentSettingsRef} tabIndex={-1} className="document-context-panel document-settings-panel" aria-labelledby="document-details-heading"><div className="section-heading"><h2 id="document-details-heading">{translate('documentation.documentSettings')}</h2><button className="icon-button" type="button" aria-label={translate('documentation.closeDocumentSettings')} onClick={() => setActivePanel(null)}><X size={16} /></button></div><div className="document-detail-fields"><label>Title<input maxLength={240} required value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>Category<select value={category} onChange={(event) => setCategory(event.target.value as DocumentCategory)}>{categories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label className="checkbox-field"><input type="checkbox" checked={isTemplate} onChange={(event) => setIsTemplate(event.target.checked)} />Reusable template</label>{!workspace && <label className="checkbox-field"><input type="checkbox" checked={libraryVisible} onChange={(event) => setLibraryVisible(event.target.checked)} />Make reusable content findable in client documents</label>}</div><div className="document-actions"><button className="primary-button" type="button" disabled={saving || !title.trim()} onClick={() => { void save() }}>{saving ? 'Saving…' : 'Save settings'}</button>{selected.is_template && <button className="secondary-button" type="button" onClick={() => { void instantiateSelectedTemplate() }}><Copy size={15} />{translate('documentation.useTemplate')}</button>}{selected.template_enrollment_id && <button className="secondary-button" type="button" onClick={() => { void previewSelectedTemplateRollout() }}><History size={15} />{translate('documentation.checkTemplateUpdates')}</button>}{selected.placement_count === 1 && <button className="secondary-button" type="button" onClick={() => { void previewRestructure() }}><List size={15} />{translate('documentation.reviewSectionConversion')}</button>}<button className="secondary-button" type="button" onClick={() => { setActivePanel('remote'); void openRemoteSource() }}><Globe2 size={15} />{translate('documentation.remoteSource')}</button>{!workspace && <button className="secondary-button" type="button" onClick={() => setActivePanel('share')}><Share2 size={15} />{translate('documentation.clientListings')}</button>}{relationshipsClient && <button className="secondary-button" type="button" onClick={() => setActivePanel('relationships')}><Link2 size={15} />{translate('documentation.relatedRecords')}</button>}<button className="danger-button" type="button" disabled={saving} onClick={() => { void archive() }}><Archive size={15} />{translate('common.archive')}</button></div></section>}
        {activePanel === 'details' && client.updateOperations && <section className="document-context-panel document-operations" aria-labelledby="document-operations-heading"><div className="section-heading"><div><h2 id="document-operations-heading">{translate('documentation.ownershipAndReview')}</h2><p>{translate('documentation.healthSummary', { status: (selected.health_status ?? 'unreviewed').replaceAll('_', ' ') })}</p></div></div><div className="document-detail-fields"><label>{translate('documentation.owner')}<select value={operationsDraft.ownerId} onChange={(event) => setOperationsDraft({ ...operationsDraft, ownerId: event.target.value })}><option value="">{translate('documentation.noOwner')}</option>{operationsChoices.map((choice) => <option key={choice.id} value={choice.id}>{choice.display_name}</option>)}</select></label><label>{translate('documentation.reviewDue')}<input type="date" value={operationsDraft.reviewDueOn} onChange={(event) => setOperationsDraft({ ...operationsDraft, reviewDueOn: event.target.value })} /></label><label>{translate('documentation.collection')}<input maxLength={120} value={operationsDraft.collection} onChange={(event) => setOperationsDraft({ ...operationsDraft, collection: event.target.value })} /></label><label>{translate('documentation.tags')}<input maxLength={400} value={operationsDraft.tags} onChange={(event) => setOperationsDraft({ ...operationsDraft, tags: event.target.value })} placeholder={translate('documentation.tagsPlaceholder')} /></label></div><div className="document-actions"><button className="secondary-button" type="button" disabled={saving} onClick={() => { void saveOperations() }}>{translate('documentation.saveOperations')}</button></div>{client.requestReview && <div className="document-review-form"><h3>{translate('documentation.requestReview')}</h3><label>{translate('documentation.reviewer')}<select value={reviewDraft.reviewerId} onChange={(event) => setReviewDraft({ ...reviewDraft, reviewerId: event.target.value })}><option value="">{translate('documentation.chooseReviewer')}</option>{operationsChoices.filter((choice) => choice.can_approve).map((choice) => <option key={choice.id} value={choice.id}>{choice.display_name}</option>)}</select></label><label>{translate('documentation.reviewNote')}<textarea maxLength={500} value={reviewDraft.note} onChange={(event) => setReviewDraft({ ...reviewDraft, note: event.target.value })} /></label><button className="secondary-button" type="button" disabled={saving || !reviewDraft.reviewerId} onClick={() => { void requestReview() }}>{translate('documentation.sendForReview')}</button></div>}{selected.review_state === 'pending' && client.decideReview && <div className="document-review-form"><h3>{translate('documentation.pendingReview')}</h3><p>{translate('documentation.assignedReviewer', { reviewer: selected.reviewer_name ?? translate('documentation.unknownReviewer') })}</p><label>{translate('documentation.decision')}<select value={decisionDraft.decision} onChange={(event) => setDecisionDraft({ ...decisionDraft, decision: event.target.value as typeof decisionDraft.decision })}><option value="approved">{translate('documentation.approve')}</option><option value="changes_requested">{translate('documentation.requestChanges')}</option></select></label><label>{translate('documentation.decisionNote')}<textarea maxLength={500} required value={decisionDraft.note} onChange={(event) => setDecisionDraft({ ...decisionDraft, note: event.target.value })} /></label><button className="primary-button" type="button" disabled={saving || !decisionDraft.note.trim()} onClick={() => { void decideReview() }}>{translate('documentation.recordDecision')}</button></div>}</section>}

        {selected.primary_file && <section className="document-context-panel primary-document-file" aria-labelledby="primary-document-file-heading"><header className="section-heading"><div><strong id="primary-document-file-heading">{selected.primary_file.filename}</strong><span>Primary file · version {selected.primary_file.version_number} · {selected.primary_file.size.toLocaleString()} bytes</span></div><div><input ref={replacementFileInput} className="sr-only" aria-label="Replacement primary file" type="file" onChange={(event) => { const file = event.target.files?.[0]; if (file) void replacePrimaryFile(file) }} />{selected.primary_file.media_type === 'application/pdf' && !viewedPdf && <button className="secondary-button" type="button" onClick={() => setViewedPdf({ filename: selected.primary_file!.filename, url: client.attachmentDownloadUrl(scope, selected.id, selected.primary_file!.id) })}>{translate('documentation.viewPdf')}</button>}<a className="secondary-button" href={client.attachmentDownloadUrl(scope, selected.id, selected.primary_file.id)}><Download size={15} />Download</a><button className="secondary-button" type="button" disabled={saving} onClick={() => replacementFileInput.current?.click()}><RefreshCw size={15} />{translate('documentation.replaceFile')}</button></div></header>{viewedPdf && <Suspense fallback={<p role="status">Loading PDF viewer…</p>}><PdfViewer filename={viewedPdf.filename} url={viewedPdf.url} onClose={() => setViewedPdf(null)} /></Suspense>}</section>}

        {activePanel === 'details' && <section className="document-context-panel document-topic-settings" aria-labelledby="document-topic-heading"><div className="section-heading"><div><h2 id="document-topic-heading">{translate('documentation.documentType')}</h2><p>{topicTypes.find((item) => item.value === selected.topic_type)?.description ?? topicTypes[0].description}</p></div></div><label>{translate('documentation.guidedStructure')}<select value={selected.topic_type ?? 'unstructured'} disabled={saving} onChange={(event) => { void changeTopic(event.target.value as DocumentTopicType) }}>{topicTypes.map((topic) => <option key={topic.value} value={topic.value}>{topic.label}</option>)}</select></label><p className="field-hint">{translate('documentation.topicChangeHelp')}</p></section>}

        <section className="document-context-panel document-check" aria-labelledby="document-check-heading"><div className="section-heading"><div><h2 id="document-check-heading">{translate('documentation.documentationCheck')}</h2><p>{translate('documentation.documentationCheckHelp')}</p></div><button className="secondary-button" type="button" disabled={documentCheck?.phase === 'loading'} onClick={() => { void runDocumentCheck() }}>{documentCheck?.phase === 'loading' ? translate('documentation.checking') : translate('documentation.checkDocument')}</button></div>{documentCheck?.phase === 'error' && <p role="alert">{translate('documentation.checkUnavailable')}</p>}{documentCheck?.phase === 'ready' && documentCheck.report && <><p role="status">{documentCheck.report.valid ? translate('documentation.noPublicationBlockers') : translate('documentation.publicationBlockerCount', { count: documentCheck.report.counts.blocker })}</p>{documentCheck.report.findings.length > 0 && <ul>{documentCheck.report.findings.map((finding, index) => <li key={`${finding.code}-${finding.section_id ?? ''}-${index}`}><strong>{finding.summary}</strong><span>{finding.remediation}</span></li>)}</ul>}</>}</section>

        <article className="document-page">
          <div className="audience-preview"><label>{translate('documentation.previewAudience')}<select value={audiencePreview} onChange={(event) => { setAudiencePreview(event.target.value as 'all' | PublicationAudience); setEditingBlock(null) }}><option value="all">{translate('documentation.previewAll')}</option><option value="msp_internal">{translate('documentation.previewMsp')}</option><option value="client_visible">{translate('documentation.previewClient')}</option></select></label><span>{translate('documentation.previewCount', { count: displayedPlacements.length })}</span></div>
          <ol className="document-content" aria-label="Document content">{displayedPlacements.map((placement) => <li className={editingBlock?.placement.id === placement.id ? 'document-content-item editing' : 'document-content-item'} key={placement.id} style={{ marginInlineStart: `${placement.depth * 18}px` }}>
            <div className="document-content-row">
              <div className="document-content-body">
                <span className={`placement-audience placement-audience-${placement.audience_profile}`}>{placementAudienceLabel(placement.audience_profile)}</span>
                {editingBlock?.placement.id === placement.id ? <div className="document-inline-editor"><Suspense fallback={<p role="status">Loading editor…</p>}><Editor key={`${placement.id}-${placement.resolved_revision_id}-${editorGeneration}`} initialMarkdown={editingBlock.draft} title="Edit content" description="" organizationId={workspace?.id} documentId={selected.id} onMarkdownChange={(draft) => setEditingBlock({ placement, draft })} /></Suspense><div className="document-actions"><button className="primary-button" type="button" disabled={saving || editingBlock.draft === placement.resolved_markdown} onClick={() => { void saveBlockEdit() }}>{saving ? 'Saving…' : 'Save'}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setEditingBlock(null)}>{translate('common.cancel')}</button></div></div> : <SanitizedMarkdown html={placement.resolved_html} />}
              </div>
              {audiencePreview === 'all' && editingBlock?.placement.id !== placement.id && <div className="document-content-controls"><button className="icon-button" type="button" aria-label="Edit this content" onClick={() => beginBlockEdit(placement)}><Pencil size={15} /></button><details><summary className="icon-button" aria-label="More content actions"><Ellipsis size={17} /></summary><div><button type="button" onClick={() => { void reviewPlacement(placement.id) }}><Share2 size={14} />{translate('documentation.reuseAndImpact')}</button>{!placement.is_primary && <>{placement.resolution_mode === 'live' ? <button type="button" onClick={() => { void changePlacementMode(placement.id, 'pinned', placement.resolved_revision_id) }}><Pin size={14} />{translate('documentation.keepThisVersion')}</button> : <button type="button" onClick={() => { void changePlacementMode(placement.id, 'live', placement.resolved_revision_id) }}><Link2 size={14} />{translate('documentation.followUpdates')}</button>}<button type="button" disabled={saving || placement.audience_profile === 'shared'} onClick={() => { void changePlacementAudience(placement.id, 'shared') }}><ShieldCheck size={14} />{translate('documentation.setAudienceShared')}</button><button type="button" disabled={saving || placement.audience_profile === 'msp_internal'} onClick={() => { void changePlacementAudience(placement.id, 'msp_internal') }}><ShieldCheck size={14} />{translate('documentation.setAudienceMsp')}</button><button type="button" disabled={saving || placement.audience_profile === 'client_visible'} onClick={() => { void changePlacementAudience(placement.id, 'client_visible') }}><ShieldCheck size={14} />{translate('documentation.setAudienceClient')}</button><button type="button" onClick={() => { void removePlacement(placement.id) }}><Unlink size={14} />{translate('documentation.removeFromDocument')}</button></>}</div></details></div>}
            </div>
            {audiencePreview === 'all' && insertionPoint(placement.position + 1)}
          </li>)}</ol>
        </article>

        {reuseReview && <section className="document-context-panel reuse-impact" aria-labelledby="reuse-impact-heading"><div className="section-heading"><div><h2 id="reuse-impact-heading">Where this content is used</h2><p>{reuseReview.impact.live_audience_count} live use{reuseReview.impact.live_audience_count === 1 ? '' : 's'} will update; {reuseReview.impact.pinned_audience_count} retained use{reuseReview.impact.pinned_audience_count === 1 ? '' : 's'} will stay unchanged.</p></div><button className="icon-button" type="button" aria-label="Close reuse details" onClick={() => setReuseReview(null)}><X size={16} /></button></div><ul>{reuseReview.impact.audiences.map((audience, index) => <li key={`${audience.relationship}-${audience.document_id}-${audience.workspace_id}-${index}`}><span><strong>{audience.document_title}</strong><small>{audience.workspace_name}</small></span><span className={audience.will_update ? 'impact-live' : 'impact-pinned'}>{audience.will_update ? 'Will update' : 'Unchanged'}</span></li>)}</ul>{reuseReview.impact.can_edit_shared && <button className="primary-button" type="button" disabled={saving} onClick={() => { void saveSharedBlock() }}>{translate('documentation.applyThisEditEverywhere')}</button>}{reuseReview.impact.can_detach && <button className="secondary-button" type="button" disabled={saving} onClick={() => { void detachPlacement() }}><Copy size={14} />{translate('documentation.makeAnIndependentCopyHere')}</button>}</section>}
        {conflict && <div className="revision-conflict" role="alert"><strong>Newer content detected</strong><p>Your draft remains open. Reconcile it with the newer changes before saving.</p>{conflict.payload.diff && <pre>{conflict.payload.diff}</pre>}<button className="secondary-button" type="button" onClick={acknowledgeConflict}>{translate('documentation.iReconciledTheseChanges')}</button></div>}

        {activePanel === 'restructure' && <section className="document-context-panel document-restructure" aria-labelledby="document-restructure-heading"><div className="section-heading"><div><h2 id="document-restructure-heading">Separate legacy content</h2><p>Preview safe section boundaries before changing this document.</p></div><button className="icon-button" type="button" aria-label="Close section conversion" onClick={() => setActivePanel(null)}><X size={16} /></button></div>{restructurePhase === 'loading' && <p role="status">Reviewing document dependencies…</p>}{restructurePhase === 'error' && <p role="alert">The section preview is unavailable.</p>}{restructurePhase === 'ready' && restructurePreview && <>{restructurePreview.blockers.length > 0 && <div className="document-restructure-notices" role="alert"><strong>This document was not changed.</strong><ul>{restructurePreview.blockers.map((item) => <li key={item.code}>{item.detail}</li>)}</ul></div>}{restructurePreview.warnings.length > 0 && <div className="document-restructure-notices"><strong>Retained dependencies</strong><ul>{restructurePreview.warnings.map((item) => <li key={item.code}>{item.detail}</li>)}</ul></div>}{restructurePreview.eligible && <><p>The current content will become {restructurePreview.section_count} independently editable sections. Their order, document ownership, files, relationships, and prior revisions remain unchanged.</p><ol className="document-restructure-sections">{restructurePreview.sections.map((section) => <li key={`${section.position}-${section.checksum}`}><details><summary><strong>{section.name.replace(`${selected.title} — `, '')}</strong><span>{blockKinds.find((item) => item.value === section.kind)?.label ?? section.kind}</span></summary><pre>{section.markdown}</pre></details></li>)}</ol><div className="document-actions"><button className="primary-button" type="button" disabled={saving} onClick={() => { void applyRestructure() }}>{saving ? 'Separating…' : `Create ${restructurePreview.section_count} sections`}</button><button className="secondary-button" type="button" disabled={saving} onClick={() => setActivePanel(null)}>{translate('common.cancel')}</button></div></>}</>}</section>}

        {activePanel === 'export' && <section className="document-context-panel document-export-panel" aria-labelledby="document-export-heading"><div className="section-heading"><div><h2 id="document-export-heading">Export editable snapshot</h2><p>Each download resolves one exact set of authorized revisions. It is editable output, not a retained STATIC publication.</p></div><button className="icon-button" type="button" aria-label="Close export" onClick={() => setActivePanel(null)}><X size={16} /></button></div><div className="document-actions"><a className="secondary-button" href={client.exportUrl(scope, selected.id, 'md')}><Download size={15} />Markdown</a><a className="secondary-button" href={client.exportUrl(scope, selected.id, 'html')}><Download size={15} />HTML</a><a className="secondary-button" href={client.exportUrl(scope, selected.id, 'pdf')}><Download size={15} />PDF</a><a className="secondary-button" href={client.exportUrl(scope, selected.id, 'docx')} title="Compatible with Microsoft Word, LibreOffice, and Google Docs import"><Download size={15} />DOCX</a></div><div className="portable-export"><h3>Portable ZIP</h3><p>The ZIP always contains canonical Markdown, sanitized HTML, and an exact-revision manifest. Select private files only when the recipient is authorized to receive them.</p>{exportableFiles.length > 0 && <fieldset><legend>Include files</legend>{exportableFiles.map((attachment) => <div key={attachment.id}><label className="checkbox-field"><input type="checkbox" checked={exportAttachmentIds.includes(attachment.id)} onChange={() => toggleExportFile(attachment.id)} /><span><strong>{attachment.filename}</strong><small>{'version_number' in attachment && typeof attachment.version_number === 'number' ? `Primary file · version ${attachment.version_number}` : 'Attachment'} · {attachment.size.toLocaleString()} bytes</small></span></label></div>)}</fieldset>}<a className="primary-button" href={client.exportUrl(scope, selected.id, 'bundle', exportAttachmentIds)}><Download size={15} />Download portable ZIP</a></div></section>}
        {activePanel === 'keys' && <section className="document-context-panel document-keys" aria-labelledby="document-keys-heading">
          <div className="section-heading">
            <div><h2 id="document-keys-heading">{translate('documentation.keysPanel')}</h2></div>
            <button className="icon-button" type="button" aria-label={translate('documentation.closeKeys')} onClick={() => setActivePanel(null)}><X size={16} /></button>
          </div>
          <div className="entity-mention-picker">
            <label><span>{translate('documentation.declareBinding')}</span><input type="text" value={bindingName} onChange={(event) => setBindingName(event.target.value.toLowerCase())} placeholder="subject" aria-label={translate('documentation.declareBinding')} aria-describedby="binding-name-rule" aria-invalid={bindingName.length > 0 && !bindingNameValid} /></label>
            <p id="binding-name-rule" className="field-hint" role={bindingName.length > 0 && !bindingNameValid ? 'alert' : undefined}>{translate('documentation.bindingNameRule')}</p>
            <label><Search size={15} /><span>{translate('documentation.tekdocsRecord')}</span><input type="search" value={mentionQuery} onChange={(event) => { setMentionQuery(event.target.value); if (!event.target.value.trim()) setMentionOptions([]) }} /></label>
            {mentionOptions.length > 0 && <ul>{mentionOptions.map((entity) => <li key={entity.id}><button type="button" disabled={saving || !bindingNameValid || !bindingTargetable(entity.entity_type)} onClick={() => { void declareBinding(entity) }}><strong>{entity.display_name}</strong><small>{bindingTargetable(entity.entity_type) ? `${entity.entity_type.replaceAll('_', ' ')} · ${entity.workspace_label}` : translate('documentation.recordNotAddressable')}</small></button></li>)}</ul>}
          </div>
          {keyBindings.length > 0 && <div className="key-bindings" role="group" aria-label={translate('documentation.keyBindingsTable')}>
            <ul>{keyBindings.map((binding) => <li key={binding.id}>
              <span><strong>{binding.name}</strong><small>{binding.target_display_name} · {binding.target_entity_type.replaceAll('_', ' ')}</small>{binding.also_bound_by.length > 0 && <small className="key-where-used">{translate('documentation.alsoUsedBy')}: {binding.also_bound_by.map((item) => item.title).join(', ')}</small>}</span>
              <div>
                <label className="sr-only" htmlFor={`key-field-${binding.id}`}>{binding.name}</label>
                <select id={`key-field-${binding.id}`} defaultValue="" onChange={(event) => { if (event.target.value) { insertKey(binding, event.target.value); event.target.value = '' } }}>
                  <option value="">{translate('documentation.insertKey')}</option>
                  {binding.addressable_fields.map((path) => <option key={path} value={path}>{path}</option>)}
                </select>
                <button className="icon-button" type="button" aria-label={`${translate('documentation.retireBinding')} ${binding.name}`} disabled={saving} onClick={() => { void retireBinding(binding.id) }}><Trash2 size={15} /></button>
              </div>
            </li>)}</ul>
          </div>}
          {keyReport && keyReport.count > 0 && <div className="key-report" role="group" aria-label={translate('documentation.keyReportTable')}>
            <ul>{keyReport.results.map((row) => <li key={row.expression} data-key-state={row.state}>
              <span><strong>{row.expression}</strong><small>{row.state === 'resolved' ? row.label : `${row.label} · ${row.reason ?? row.state}`}</small></span>
            </li>)}</ul>
          </div>}
          {keyReport && keyReport.count === 0 && <p className="empty-state">{translate('documentation.keysPanel')}</p>}
          <div className="key-browser">
            <label><Search size={15} /><span>{translate('documentation.findBindings')}</span><input type="search" value={bindingQuery} onChange={(event) => setBindingQuery(event.target.value)} /></label>
            {bindingMatches.length > 0 && <ul aria-label={translate('documentation.bindingBrowserTable')}>{bindingMatches.map((match) => <li key={match.id}><span><strong>{match.target_display_name}</strong><small>{match.document_title} · {match.name}</small></span></li>)}</ul>}
          </div>
        </section>}
        {activePanel === 'files' && <section className="document-context-panel document-attachments" aria-labelledby="document-attachments-heading"><div className="section-heading"><div><h2 id="document-attachments-heading">Files</h2><p>Private files are scanned before they become available.</p></div><div><input ref={attachmentInput} aria-label="Attachment file" className="sr-only" type="file" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadAttachment(file) }} /><button className="secondary-button" type="button" disabled={saving} onClick={() => attachmentInput.current?.click()}><Paperclip size={15} />{translate('documentation.addFile')}</button><button className="icon-button" type="button" aria-label="Close files" onClick={() => setActivePanel(null)}><X size={16} /></button></div></div>{selected.primary_file_versions.length > 0 && <div className="primary-file-history"><h3>Primary file versions</h3><ul>{selected.primary_file_versions.map((version) => { const downloadUrl = client.attachmentDownloadUrl(scope, selected.id, version.id); return <li key={version.id}><span><strong>{version.filename}</strong><small>Version {version.version_number}{version.is_current ? ' · Current' : ''} · {version.size.toLocaleString()} bytes</small></span><div>{version.media_type === 'application/pdf' && <button className="secondary-button" type="button" onClick={() => setViewedPdf({ filename: version.filename, url: downloadUrl })}>{translate('documentation.viewPdf')}</button>}<a className="secondary-button" href={downloadUrl}>Download</a></div></li> })}</ul></div>}{selected.attachments.length === 0 ? <p className="empty-state">No additional files attached.</p> : <ul>{selected.attachments.map((attachment) => { const downloadUrl = client.attachmentDownloadUrl(scope, selected.id, attachment.id); return <li key={attachment.id}><a href={downloadUrl}><strong>{attachment.filename}</strong><small>{attachment.media_type} · {attachment.size.toLocaleString()} bytes</small></a><div>{attachment.media_type === 'application/pdf' && <button className="secondary-button" type="button" onClick={() => setViewedPdf({ filename: attachment.filename, url: downloadUrl })}>{translate('documentation.viewPdf')}</button>}<button className="secondary-button" type="button" onClick={() => insertAttachment(attachment.id, attachment.filename)}>{translate('documentation.insertHere')}</button><button className="icon-button" type="button" aria-label={`Remove ${attachment.filename}`} onClick={() => { void removeAttachment(attachment.id) }}><Trash2 size={15} /></button></div></li> })}</ul>}{viewedPdf && !selected.primary_file && <Suspense fallback={<p role="status">Loading PDF viewer…</p>}><PdfViewer filename={viewedPdf.filename} url={viewedPdf.url} onClose={() => setViewedPdf(null)} /></Suspense>}</section>}

        {activePanel === 'reuse' && <section className="document-context-panel" aria-labelledby="insert-existing-heading"><div className="section-heading"><div><h2 id="insert-existing-heading">Insert existing content</h2><p>Use content that follows its source, or retain the current version.</p></div><button className="icon-button" type="button" aria-label="Close existing content" onClick={() => setActivePanel(null)}><X size={16} /></button></div><div className="reuse-resolution"><label>Update behavior<select value={placementMode} onChange={(event) => setPlacementMode(event.target.value as 'live' | 'pinned')}><option value="live">Follow source updates</option><option value="pinned">Keep the current version</option></select></label><label>{translate('documentation.audienceLabel')}<select value={placementAudience} onChange={(event) => setPlacementAudience(event.target.value as PlacementAudienceProfile)}><option value="shared">{translate('documentation.audienceShared')}</option><option value="msp_internal">{translate('documentation.audienceMspInternal')}</option><option value="client_visible">{translate('documentation.audienceClientVisible')}</option></select></label><label>Find reusable content<input type="search" value={blockLibraryQuery} onChange={(event) => setBlockLibraryQuery(event.target.value)} placeholder="Search by content or document" /></label></div>{blockLibrary.length > 0 && <ul className="reuse-results">{blockLibrary.map((block) => <li key={block.id}><span><strong>{block.name.replace(/ — content$/, '')}</strong><small>{block.source_document_title} · {block.owner_kind === 'msp' ? 'MSP' : 'This client'}</small></span><button className="secondary-button" type="button" onClick={() => { void reuseLibraryBlock(block) }}>{translate('documentation.insert')}</button></li>)}</ul>}<div className="reuse-document"><label>Link a document<select value={sourceDocumentId} onChange={(event) => setSourceDocumentId(event.target.value)}><option value="">Choose a visible document</option>{results.filter((item) => item.id !== selected.id).map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><button className="secondary-button" type="button" disabled={!sourceDocumentId || saving} onClick={() => { void addPlacement() }}>{translate('documentation.insertDocument')}</button></div><div className="entity-mention-picker"><label><Search size={15} /><span>Link a TekDocs record</span><input type="search" placeholder="Search people, sites, assets, networks…" value={mentionQuery} onChange={(event) => { setMentionQuery(event.target.value); if (!event.target.value.trim()) setMentionOptions([]) }} /></label>{mentionOptions.length > 0 && <ul>{mentionOptions.map((entity) => <li key={entity.id}><button type="button" onClick={() => insertMention(entity)}><strong>{entity.display_name}</strong><small>{entity.entity_type.replaceAll('_', ' ')} · {entity.workspace_label}</small></button></li>)}</ul>}</div></section>}

        {activePanel === 'history' && <section className="document-context-panel revision-history" aria-labelledby="revision-history-heading"><div className="section-heading"><div><h2 id="revision-history-heading">Revision history</h2><p>{historyCount} retained revision{historyCount === 1 ? '' : 's'} · page {historyPage}</p></div><button className="icon-button" type="button" aria-label="Close revision history" onClick={() => setActivePanel(null)}><X size={16} /></button></div>{historyPhase === 'loading' && <p role="status">Loading revision history…</p>}{historyPhase === 'error' && <p role="alert">Revision history is unavailable.</p>}{historyPhase === 'ready' && <><div className="revision-history-body"><ol>{history.map((item) => <li key={item.id}><button type="button" onClick={() => { void inspectRevision(item) }}><strong>Revision {item.revision_number}</strong>{item.is_current && <span>Current</span>}<small>{item.created_by ?? 'System'} · {new Date(item.created_at).toLocaleString()}</small></button></li>)}</ol><div className="revision-diff">{viewedRevision ? <><h3>Revision {viewedRevision.revision_number}</h3><pre tabIndex={0}>{viewedRevision.diff_from_parent || 'No line changes.'}</pre></> : <p>Select a revision to inspect its changes.</p>}</div></div><nav className="history-pagination" aria-label="Revision history pages"><button className="secondary-button" type="button" disabled={historyPage === 1} onClick={() => { void loadHistory(selected, historyPage - 1) }}>{translate('documentation.newer')}</button><button className="secondary-button" type="button" disabled={!historyHasMore} onClick={() => { void loadHistory(selected, historyPage + 1) }}>{translate('documentation.older')}</button></nav></>}</section>}

        {activePanel === 'share' && !workspace && <section className="document-context-panel document-share" aria-labelledby="client-listings-heading"><div><Share2 size={16} /><span><strong id="client-listings-heading">Client listings</strong><small>The MSP remains the owner; no document is copied.</small></span><button className="icon-button" type="button" aria-label="Close client listings" onClick={() => setActivePanel(null)}><X size={16} /></button></div><label><span className="sr-only">Find client organization</span><input type="search" placeholder="Find a client" value={shareQuery} onChange={(event) => setShareQuery(event.target.value)} /></label>{shareOptions.length > 0 && <ul>{shareOptions.map((organization) => <li key={organization.id}><button type="button" disabled={saving} onClick={() => { void share(organization) }}>{organization.name}<ExternalLink size={14} /></button></li>)}</ul>}</section>}
        {activePanel === 'relationships' && relationshipsClient && <section className="document-context-panel"><div className="section-heading"><h2>Related records</h2><button className="icon-button" type="button" aria-label="Close related records" onClick={() => setActivePanel(null)}><X size={16} /></button></div><DocumentRelationshipRail scope={scope} documentId={selected.id} client={relationshipsClient} /><RelationshipGraph scope={scope} family="document" rootId={selected.id} client={relationshipsClient} heading="Document relationships" /></section>}
        {activePanel === 'remote' && remoteSourceOpen && <section className="document-context-panel remote-source" aria-labelledby="remote-source-heading"><div className="section-heading"><div><h2 id="remote-source-heading">Remote source</h2><p>Monitor a public HTTPS page. Changes require review.</p></div><button className="icon-button" type="button" aria-label="Close remote source" onClick={() => { setRemoteSourceOpen(false); setActivePanel(null) }}><X size={16} /></button></div><label>Public document URL<input type="url" value={remoteSourceDraft.url} onChange={(event) => setRemoteSourceDraft({ ...remoteSourceDraft, url: event.target.value })} placeholder="https://example.com/document" /></label><div className="new-block-fields"><label>Source format<select value={remoteSourceDraft.source_kind} onChange={(event) => setRemoteSourceDraft({ ...remoteSourceDraft, source_kind: event.target.value as 'auto' | 'markdown' | 'html' })}><option value="auto">Detect automatically</option><option value="markdown">Markdown</option><option value="html">HTML</option></select></label><label>Check interval (minutes)<input type="number" min="15" max="10080" value={remoteSourceDraft.check_interval_minutes} onChange={(event) => setRemoteSourceDraft({ ...remoteSourceDraft, check_interval_minutes: Number(event.target.value) })} /></label></div><label className="checkbox-field"><input type="checkbox" checked={remoteSourceDraft.enabled} onChange={(event) => setRemoteSourceDraft({ ...remoteSourceDraft, enabled: event.target.checked })} />Scheduled checks enabled</label><div className="document-actions"><button className="primary-button" type="button" disabled={saving || !remoteSourceDraft.url} onClick={() => { void saveRemoteSource() }}>{translate('documentation.saveSource')}</button>{remoteSource && <button className="secondary-button" type="button" onClick={() => { void checkRemoteSource() }}><RefreshCw size={15} />{translate('documentation.checkNow')}</button>}</div>{remoteObservations.length > 0 && <ol className="remote-observations">{remoteObservations.map((observation) => <li key={observation.id}><header><strong>{observation.state === 'changed' ? 'Change detected' : observation.state === 'failed' ? 'Check failed' : 'No change'}</strong><span>{new Date(observation.fetched_at).toLocaleString()}</span></header>{observation.diff && <pre>{observation.diff}</pre>}{observation.state === 'changed' && observation.id !== remoteSource?.last_applied_observation_id && <button className="secondary-button" type="button" onClick={() => { void applyRemoteObservation(observation) }}>{translate('documentation.applyReviewedChange')}</button>}</li>)}</ol>}</section>}
        {templateRollout && <section className="document-context-panel template-rollout"><div className="section-heading"><div><h2>Template updates</h2><p>Applied revision {templateRollout.current_revision}; available revision {templateRollout.available_revision}.</p></div><button className="icon-button" type="button" aria-label="Close template updates" onClick={() => setTemplateRollout(null)}><X size={16} /></button></div>{templateRollout.up_to_date ? <p>This document is current with its template.</p> : <button className="primary-button" type="button" disabled={saving || templateRollout.conflicts.length > 0} onClick={() => { void applySelectedTemplateRollout() }}>{translate('documentation.applySafeChanges')}</button>}</section>}
      </>}
    </section>}
  </>
}
