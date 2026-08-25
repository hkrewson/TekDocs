import { useEffect, useMemo, useState } from "react";
import { translate} from '../i18n/localization'
import { DataFlows } from './DataFlows'
import type { DataFlowClient } from './dataFlowApi'
import { History, Plus, Search, Trash2 } from "lucide-react";

import { CollectionPagination } from "../CollectionPagination";
import type { WorkspaceContext } from "../workspaces/api";
import type {
  ComplianceCatalogDraft,
  ComplianceCatalogRevision,
  ComplianceAssignment,
  ComplianceAssignmentDraft,
  ComplianceClient,
  ComplianceControlDraft,
  ComplianceEvidence,
  ComplianceEvidenceDraft,
  ComplianceFramework,
  ComplianceFrameworkDraft,
  ComplianceOwnerChoice,
  ComplianceRisk,
  ComplianceRiskDraft,
  ComplianceRiskResult,
  ComplianceBundle,
} from "./api";

const EMPTY_CONTROL: ComplianceControlDraft = {
  identifier: "",
  title: "",
  description: "",
  guidance: "",
};
const EMPTY_CATALOG: ComplianceCatalogDraft = {
  version_label: "",
  description: "",
  source_url: "",
  controls: [],
};
const EMPTY_ASSIGNMENT: ComplianceAssignmentDraft = {
  applicability: "unassessed",
  implementation_status: "not_started",
  owner_id: null,
  review_due_date: null,
  decision: "",
  note: "",
};
const EMPTY_EVIDENCE: ComplianceEvidenceDraft = {
  title: "",
  kind: "note",
  summary: "",
  source_url: "",
  source_entity_id: null,
  collection_start: null,
  collection_end: null,
};
const EMPTY_RISK: ComplianceRiskDraft = {
  title: "", description: "", assignment_id: null, likelihood: 3, impact: 3,
  status: "open", treatment: "mitigate", treatment_plan: "", owner_id: null,
  due_date: null, decision: "", note: "",
};

function controlsFrom(
  revision: ComplianceCatalogRevision,
): ComplianceControlDraft[] {
  return revision.entries.map(({ control }) => ({
    control_id: control.control_id,
    identifier: control.identifier,
    title: control.title,
    description: control.description,
    guidance: control.guidance,
  }));
}

function CatalogForm({
  draft,
  setDraft,
  saving,
  onSave,
  onCancel,
  submitLabel,
}: {
  draft: ComplianceCatalogDraft;
  setDraft: (draft: ComplianceCatalogDraft) => void;
  saving: boolean;
  onSave: () => void;
  onCancel: () => void;
  submitLabel: string;
}) {
  function updateControl(
    index: number,
    patch: Partial<ComplianceControlDraft>,
  ) {
    setDraft({
      ...draft,
      controls: draft.controls.map((item, position) =>
        position === index ? { ...item, ...patch } : item,
      ),
    });
  }
  return (
    <>
      <div className="compliance-catalog-fields">
        <label>
          <span>Version label</span>
          <input
            value={draft.version_label}
            maxLength={100}
            onChange={(event) =>
              setDraft({ ...draft, version_label: event.target.value })
            }
            placeholder="2026.1"
          />
        </label>
        <label>
          <span>Source URL (optional)</span>
          <input
            type="url"
            value={draft.source_url}
            maxLength={500}
            onChange={(event) =>
              setDraft({ ...draft, source_url: event.target.value })
            }
          />
        </label>
        <label className="wide-field">
          <span>Version description</span>
          <textarea
            value={draft.description}
            onChange={(event) =>
              setDraft({ ...draft, description: event.target.value })
            }
            rows={3}
          />
        </label>
      </div>
      <div className="compliance-controls-heading">
        <div>
          <h3>Controls</h3>
          <p>Each saved version pins this exact ordered content.</p>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={() =>
            setDraft({
              ...draft,
              controls: [...draft.controls, { ...EMPTY_CONTROL }],
            })
          }
        >
          <Plus size={15} />
          {translate('compliance.addControl')}
        </button>
      </div>
      {draft.controls.length === 0 ? (
        <p className="empty-state">This version has no controls yet.</p>
      ) : (
        <ol className="compliance-control-editor">
          {draft.controls.map((item, index) => (
            <li key={item.control_id ?? `new-${index}`}>
              <div className="compliance-control-title">
                <label>
                  <span>Identifier</span>
                  <input
                    value={item.identifier}
                    maxLength={100}
                    onChange={(event) =>
                      updateControl(index, { identifier: event.target.value })
                    }
                    placeholder="AC-1"
                  />
                </label>
                <label>
                  <span>Title</span>
                  <input
                    value={item.title}
                    maxLength={240}
                    onChange={(event) =>
                      updateControl(index, { title: event.target.value })
                    }
                  />
                </label>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Remove ${item.identifier || `control ${index + 1}`}`}
                  onClick={() =>
                    setDraft({
                      ...draft,
                      controls: draft.controls.filter(
                        (_, position) => position !== index,
                      ),
                    })
                  }
                >
                  <Trash2 size={15} />
                </button>
              </div>
              <label>
                <span>Description (Markdown)</span>
                <textarea
                  rows={3}
                  value={item.description}
                  onChange={(event) =>
                    updateControl(index, { description: event.target.value })
                  }
                />
              </label>
              <label>
                <span>Implementation guidance (Markdown)</span>
                <textarea
                  rows={3}
                  value={item.guidance}
                  onChange={(event) =>
                    updateControl(index, { guidance: event.target.value })
                  }
                />
              </label>
            </li>
          ))}
        </ol>
      )}
      <div className="form-actions">
        <button
          className="primary-button"
          type="button"
          disabled={
            saving ||
            !draft.version_label ||
            draft.controls.some((item) => !item.identifier || !item.title)
          }
          onClick={onSave}
        >
          {saving ? "Saving…" : submitLabel}
        </button>
        <button
          className="secondary-button"
          type="button"
          disabled={saving}
          onClick={onCancel}
        >
          {translate('common.cancel')}
        </button>
      </div>
    </>
  );
}

export function Compliance({
  workspace,
  client,
  dataFlowClient,
}: {
  workspace: WorkspaceContext | null;
  client: ComplianceClient;
  dataFlowClient?: DataFlowClient;
}) {
  const [frameworks, setFrameworks] = useState<ComplianceFramework[]>([]);
  const [canManage, setCanManage] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [revisions, setRevisions] = useState<ComplianceCatalogRevision[]>([]);
  const [assignments, setAssignments] = useState<ComplianceAssignment[]>([]);
  const [ownerChoices, setOwnerChoices] = useState<ComplianceOwnerChoice[]>([]);
  const [evidence, setEvidence] = useState<ComplianceEvidence[]>([]);
  const [evidenceFormOpen, setEvidenceFormOpen] = useState(false);
  const [evidenceDraft, setEvidenceDraft] = useState<ComplianceEvidenceDraft>(EMPTY_EVIDENCE);
  const [existingEvidenceId, setExistingEvidenceId] = useState("");
  const [evidenceAssignmentId, setEvidenceAssignmentId] = useState("");
  const [evidenceDecision, setEvidenceDecision] = useState("");
  const [risks, setRisks] = useState<ComplianceRisk[]>([]);
  const [riskSummary, setRiskSummary] = useState<ComplianceRiskResult["summary"]>({
    total: 0, overdue: 0, by_status: {}, by_band: {},
  });
  const [riskFormOpen, setRiskFormOpen] = useState(false);
  const [editingRiskId, setEditingRiskId] = useState<string | null>(null);
  const [riskDraft, setRiskDraft] = useState<ComplianceRiskDraft>(EMPTY_RISK);
  const [bundles, setBundles] = useState<ComplianceBundle[]>([]);
  const [reviewingControl, setReviewingControl] = useState<string | null>(null);
  const [assignmentDraft, setAssignmentDraft] =
    useState<ComplianceAssignmentDraft>(EMPTY_ASSIGNMENT);
  const [viewingRevision, setViewingRevision] = useState<number | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageState, setPageState] = useState({
    pageSize: 50,
    count: 0,
    hasMore: false,
  });
  const [form, setForm] = useState<"new" | "version" | null>(null);
  const [frameworkName, setFrameworkName] = useState("");
  const [draft, setDraft] = useState<ComplianceCatalogDraft>(EMPTY_CATALOG);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    client
      .list(workspace, query, page, controller.signal)
      .then((result) => {
        setFrameworks(result.results);
        setCanManage(result.can_manage);
        setPageState({
          pageSize: result.page_size,
          count: result.count,
          hasMore: result.has_more,
        });
        setSelectedId((current) =>
          current && result.results.some((item) => item.id === current)
            ? current
            : (result.results[0]?.id ?? null),
        );
        setPhase("ready");
      })
      .catch(() => {
        if (!controller.signal.aborted) setPhase("error");
      });
    return () => controller.abort();
  }, [client, page, query, workspace]);

  const selected = useMemo(
    () => frameworks.find((item) => item.id === selectedId) ?? null,
    [frameworks, selectedId],
  );
  const displayed =
    viewingRevision === null
      ? selected?.current_revision
      : revisions.find((item) => item.revision_number === viewingRevision);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    client
      .revisions(workspace, selectedId, controller.signal)
      .then(setRevisions)
      .catch(() => {
        if (!controller.signal.aborted)
          setError("Version history could not be loaded.");
      });
    return () => controller.abort();
  }, [client, selectedId, workspace]);

  useEffect(() => {
    const controller = new AbortController();
    client
      .evidence(workspace, controller.signal)
      .then((result) => setEvidence(result.results))
      .catch(() => {
        if (!controller.signal.aborted) setError("Compliance evidence could not be loaded.");
      });
    return () => controller.abort();
  }, [client, workspace]);
  useEffect(() => {
    const controller = new AbortController();
    client.bundles(workspace, controller.signal).then(setBundles).catch(() => {
      if (!controller.signal.aborted) setError("Evidence bundles could not be loaded.");
    });
    return () => controller.abort();
  }, [client, workspace]);

  useEffect(() => {
    const controller = new AbortController();
    client.risks(workspace, controller.signal).then((result) => {
      setRisks(result.results);
      setRiskSummary(result.summary);
      if (result.owner_choices.length) setOwnerChoices(result.owner_choices);
    }).catch(() => {
      if (!controller.signal.aborted) setError("Compliance risks could not be loaded.");
    });
    return () => controller.abort();
  }, [client, workspace]);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    client
      .assignments(workspace, selectedId, controller.signal)
      .then((result) => {
        setAssignments(result.results);
        setOwnerChoices(result.owner_choices);
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError("Control assignments could not be loaded.");
      });
    return () => controller.abort();
  }, [client, selectedId, workspace]);

  function startNew() {
    setForm("new");
    setFrameworkName("");
    setDraft({ ...EMPTY_CATALOG, controls: [{ ...EMPTY_CONTROL }] });
    setError(null);
  }

  function startVersion() {
    if (!selected) return;
    setForm("version");
    setDraft({
      version_label: "",
      description: selected.current_revision.description,
      source_url: selected.current_revision.source_url,
      controls: controlsFrom(selected.current_revision),
    });
    setError(null);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      if (form === "new") {
        const created = await client.create(workspace, {
          name: frameworkName,
          ...draft,
        } satisfies ComplianceFrameworkDraft);
        setFrameworks((current) =>
          [...current, created].sort((a, b) => a.name.localeCompare(b.name)),
        );
        setSelectedId(created.id);
        setRevisions([created.current_revision]);
      } else if (form === "version" && selected) {
        const revision = await client.createVersion(
          workspace,
          selected.id,
          draft,
        );
        setFrameworks((current) =>
          current.map((item) =>
            item.id === selected.id
              ? {
                  ...item,
                  current_revision: revision,
                  revision_count: item.revision_count + 1,
                }
              : item,
          ),
        );
        setRevisions((current) => [revision, ...current]);
        setViewingRevision(null);
      }
      setForm(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The catalog version could not be saved.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function saveAssignment() {
    if (!selected || !reviewingControl) return;
    setSaving(true);
    setError(null);
    try {
      const assignment = await client.reviewControl(
        workspace,
        selected.id,
        reviewingControl,
        assignmentDraft,
      );
      setAssignments((current) => [
        assignment,
        ...current.filter((item) => item.control_id !== assignment.control_id),
      ]);
      setReviewingControl(null);
      setAssignmentDraft(EMPTY_ASSIGNMENT);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The control review could not be saved.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function saveEvidence() {
    setSaving(true);
    setError(null);
    try {
      let evidenceId = existingEvidenceId;
      if (!evidenceId) {
        const created = await client.createEvidence(workspace, evidenceDraft);
        evidenceId = created.id;
        await client.reviewEvidence(workspace, evidenceId, {
          status: "collected",
          decision: evidenceDecision,
          note: "",
        });
      }
      if (evidenceAssignmentId) {
        await client.linkEvidence(workspace, evidenceAssignmentId, evidenceId);
      }
      const refreshed = await client.evidence(workspace);
      setEvidence(refreshed.results);
      setEvidenceFormOpen(false);
      setEvidenceDraft(EMPTY_EVIDENCE);
      setExistingEvidenceId("");
      setEvidenceAssignmentId("");
      setEvidenceDecision("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The evidence could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  function editRisk(risk: ComplianceRisk) {
    setEditingRiskId(risk.id);
    setRiskDraft({
      title: risk.title, description: risk.description, assignment_id: risk.assignment_id,
      likelihood: risk.likelihood, impact: risk.impact, status: risk.status, treatment: risk.treatment,
      treatment_plan: risk.treatment_plan, owner_id: risk.owner_id, due_date: risk.due_date,
      decision: "", note: "",
    });
    setRiskFormOpen(true);
  }

  async function saveRisk() {
    setSaving(true);
    setError(null);
    try {
      if (editingRiskId) await client.reviewRisk(workspace, editingRiskId, riskDraft);
      else await client.createRisk(workspace, riskDraft);
      const result = await client.risks(workspace);
      setRisks(result.results);
      setRiskSummary(result.summary);
      setRiskFormOpen(false);
      setEditingRiskId(null);
      setRiskDraft(EMPTY_RISK);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The risk decision could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Compliance</h1>
          <p>
            Versioned control catalogs, applicability decisions, accountable
            owners, and retained review history for this workspace.
          </p>
        </div>
        {canManage && (
          <button type="button" className="primary-button" aria-label={translate('compliance.newFramework')} title={translate('compliance.newFramework')} onClick={startNew}>
            <Plus size={16} aria-hidden="true" />
            <span className="button-label">{translate('compliance.newFramework')}</span>
          </button>
        )}
      </header>
      {error && (
        <div className="form-message error" role="alert">
          {error}
        </div>
      )}
      {form && (
        <section
          className="content-section compliance-version-form"
          aria-labelledby="catalog-form-heading"
        >
          <div className="section-heading">
            <div>
              <h2 id="catalog-form-heading">
                {form === "new"
                  ? "New framework"
                  : `New ${selected?.name} version`}
              </h2>
              <p>
                Saving creates immutable revisions; an earlier version cannot be
                overwritten.
              </p>
            </div>
          </div>
          {form === "new" && (
            <label className="compliance-framework-name">
              <span>Framework name</span>
              <input
                autoFocus
                value={frameworkName}
                maxLength={240}
                onChange={(event) => setFrameworkName(event.target.value)}
              />
            </label>
          )}
          <CatalogForm
            draft={draft}
            setDraft={setDraft}
            saving={saving}
            onSave={() => {
              void save();
            }}
            onCancel={() => setForm(null)}
            submitLabel={form === "new" ? "Create framework" : "Create version"}
          />
        </section>
      )}
      <div className="compliance-layout">
        <section className="content-section compliance-index">
          <label className="credential-reference-search">
            <span>Search frameworks</span>
            <div>
              <Search size={16} />
              <input
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setPage(1);
                  setPhase("loading");
                }}
              />
            </div>
          </label>
          {phase === "loading" && (
            <p className="empty-state" role="status">
              Loading frameworks…
            </p>
          )}
          {phase === "error" && (
            <p className="empty-state" role="alert">
              Compliance frameworks are unavailable.
            </p>
          )}
          {phase === "ready" && frameworks.length === 0 && (
            <p className="empty-state">
              No compliance frameworks have been created in this workspace.
            </p>
          )}
          {frameworks.length > 0 && (
            <ul className="compliance-framework-list">
              {frameworks.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={selected?.id === item.id ? "selected" : ""}
                    onClick={() => {
                      setSelectedId(item.id);
                      setViewingRevision(null);
                    }}
                  >
                    <strong>{item.name}</strong>
                    <span>
                      {item.current_revision.version_label} ·{" "}
                      {item.current_revision.entries.length} controls
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <CollectionPagination
            label="Compliance frameworks"
            page={page}
            pageSize={pageState.pageSize}
            count={pageState.count}
            hasMore={pageState.hasMore}
            onPageChange={setPage}
          />
        </section>
        <section className="content-section compliance-detail">
          {selected && displayed ? (
            <>
              <div className="section-heading">
                <div>
                  <h2>{selected.name}</h2>
                  <p>
                    {displayed.description ||
                      "No description for this catalog version."}
                  </p>
                </div>
                {selected.can_manage && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={startVersion}
                  >
                    <Plus size={15} />
                    {translate('compliance.newVersion')}
                  </button>
                )}
              </div>
              <div className="compliance-revision-bar">
                <label>
                  <History size={15} />
                  <span>Catalog version</span>
                  <select
                    value={displayed.revision_number}
                    onChange={(event) =>
                      setViewingRevision(
                        Number(event.target.value) ===
                          selected.current_revision.revision_number
                          ? null
                          : Number(event.target.value),
                      )
                    }
                  >
                    {revisions.map((revision) => (
                      <option
                        key={revision.revision_number}
                        value={revision.revision_number}
                      >
                        {revision.version_label} · revision{" "}
                        {revision.revision_number}
                      </option>
                    ))}
                  </select>
                </label>
                <span>
                  {viewingRevision === null ? "Current" : "Historical snapshot"}
                </span>
              </div>
              <dl className="compliance-version-metadata">
                <div>
                  <dt>Created</dt>
                  <dd>{new Date(displayed.created_at).toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Created by</dt>
                  <dd>{displayed.created_by}</dd>
                </div>
                <div>
                  <dt>Digest</dt>
                  <dd>
                    <code>{displayed.content_digest.slice(0, 16)}</code>
                  </dd>
                </div>
                {displayed.source_url && (
                  <div>
                    <dt>Source</dt>
                    <dd>
                      <a
                        href={displayed.source_url}
                        rel="noreferrer"
                        target="_blank"
                      >
                        Open source
                      </a>
                    </dd>
                  </div>
                )}
              </dl>
              {displayed.entries.length === 0 ? (
                <p className="empty-state">
                  This catalog version contains no controls.
                </p>
              ) : (
                <ol className="compliance-control-list">
                  {displayed.entries.map(({ control }) => {
                    const assignment = assignments.find(
                      (item) => item.control_id === control.control_id,
                    );
                    return (
                      <li key={control.control_id}>
                        <div>
                          <strong>{control.identifier}</strong>
                          <span>
                            {assignment
                              ? `${assignment.applicability.replace("_", " ")} · ${assignment.implementation_status.replace("_", " ")}`
                              : `Revision ${control.revision_number}`}
                          </span>
                        </div>
                        <h3>{control.title}</h3>
                        {control.description && <p>{control.description}</p>}
                        {control.guidance && (
                          <details>
                            <summary>Implementation guidance</summary>
                            <pre>{control.guidance}</pre>
                          </details>
                        )}
                        {selected.can_manage && viewingRevision === null && (
                          <button
                            type="button"
                            className="text-button"
                            onClick={() => {
                              setReviewingControl(control.control_id);
                              setAssignmentDraft(
                                assignment
                                  ? {
                                      applicability: assignment.applicability,
                                      implementation_status:
                                        assignment.implementation_status,
                                      owner_id: assignment.owner_id,
                                      review_due_date:
                                        assignment.review_due_date,
                                      decision: "",
                                      note: "",
                                    }
                                  : EMPTY_ASSIGNMENT,
                              );
                            }}
                          >
                            {translate('compliance.reviewControl')}
                          </button>
                        )}
                        {reviewingControl === control.control_id && (
                          <div className="compliance-assignment-form">
                            <label>
                              <span>Applicability</span>
                              <select
                                value={assignmentDraft.applicability}
                                onChange={(event) =>
                                  setAssignmentDraft({
                                    ...assignmentDraft,
                                    applicability: event.target
                                      .value as ComplianceAssignmentDraft["applicability"],
                                  })
                                }
                              >
                                <option value="unassessed">
                                  Not evaluated
                                </option>
                                <option value="applicable">Applicable</option>
                                <option value="not_applicable">
                                  Not applicable
                                </option>
                              </select>
                            </label>
                            <label>
                              <span>Status</span>
                              <select
                                value={assignmentDraft.implementation_status}
                                onChange={(event) =>
                                  setAssignmentDraft({
                                    ...assignmentDraft,
                                    implementation_status: event.target
                                      .value as ComplianceAssignmentDraft["implementation_status"],
                                  })
                                }
                              >
                                <option value="not_started">Not started</option>
                                <option value="planned">Planned</option>
                                <option value="in_progress">In progress</option>
                                <option value="implemented">Implemented</option>
                                <option value="not_implemented">
                                  Not implemented
                                </option>
                              </select>
                            </label>
                            <label>
                              <span>Owner</span>
                              <select
                                value={assignmentDraft.owner_id ?? ''}
                                onChange={(event) =>
                                  setAssignmentDraft({
                                    ...assignmentDraft,
                                    owner_id: event.target.value || null,
                                  })
                                }
                              >
                                <option value="">Unassigned</option>
                                {ownerChoices.map((owner) => (
                                  <option key={owner.id} value={owner.id}>
                                    {owner.display_name}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label>
                              <span>Review due</span>
                              <input
                                type="date"
                                value={assignmentDraft.review_due_date ?? ""}
                                onChange={(event) =>
                                  setAssignmentDraft({
                                    ...assignmentDraft,
                                    review_due_date: event.target.value || null,
                                  })
                                }
                              />
                            </label>
                            <label className="wide-field">
                              <span>Decision</span>
                              <input
                                maxLength={120}
                                value={assignmentDraft.decision}
                                onChange={(event) =>
                                  setAssignmentDraft({
                                    ...assignmentDraft,
                                    decision: event.target.value,
                                  })
                                }
                              />
                            </label>
                            <label className="wide-field">
                              <span>Review note (Markdown)</span>
                              <textarea
                                rows={3}
                                value={assignmentDraft.note}
                                onChange={(event) =>
                                  setAssignmentDraft({
                                    ...assignmentDraft,
                                    note: event.target.value,
                                  })
                                }
                              />
                            </label>
                            <div className="form-actions wide-field">
                              <button
                                type="button"
                                className="primary-button"
                                disabled={saving || !assignmentDraft.decision}
                                onClick={() => {
                                  void saveAssignment();
                                }}
                              >
                                {translate('compliance.saveReview')}
                              </button>
                              <button
                                type="button"
                                className="secondary-button"
                                onClick={() => setReviewingControl(null)}
                              >
                                {translate('common.cancel')}
                              </button>
                            </div>
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ol>
              )}
            </>
          ) : (
            <p className="empty-state">
              Choose a framework to inspect its current catalog.
            </p>
          )}
        </section>
      </div>
      <section className="content-section compliance-evidence" aria-labelledby="compliance-evidence-heading">
        <div className="section-heading">
          <div>
            <h2 id="compliance-evidence-heading">Evidence</h2>
            <p>Reusable workspace evidence with collection windows, exact control links, and retained reviews.</p>
          </div>
          {canManage && (
            <button type="button" className="secondary-button" onClick={() => setEvidenceFormOpen(true)}>
              <Plus size={15} /> {translate('compliance.addOrLinkEvidence')}
            </button>
          )}
        </div>
        {evidenceFormOpen && (
          <div className="compliance-evidence-form">
            <label>
              <span>Reuse existing evidence</span>
              <select value={existingEvidenceId} onChange={(event) => setExistingEvidenceId(event.target.value)}>
                <option value="">Create new evidence</option>
                {evidence.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
              </select>
            </label>
            <label>
              <span>Link to control</span>
              <select value={evidenceAssignmentId} onChange={(event) => setEvidenceAssignmentId(event.target.value)}>
                <option value="">Keep unlinked</option>
                {assignments.map((item) => <option key={item.id} value={item.id}>{item.control_identifier} — {item.control_title}</option>)}
              </select>
            </label>
            {!existingEvidenceId && <>
              <label><span>Title</span><input value={evidenceDraft.title} maxLength={240} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, title: event.target.value })} /></label>
              <label><span>Kind</span><select value={evidenceDraft.kind} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, kind: event.target.value as ComplianceEvidenceDraft["kind"], source_url: "", source_entity_id: null })}><option value="note">Recorded note</option><option value="url">External URL</option></select></label>
              {evidenceDraft.kind === "url" && <label className="wide-field"><span>Source URL</span><input type="url" value={evidenceDraft.source_url} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, source_url: event.target.value })} /></label>}
              <label><span>Collection start</span><input type="date" value={evidenceDraft.collection_start ?? ""} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, collection_start: event.target.value || null })} /></label>
              <label><span>Collection end</span><input type="date" value={evidenceDraft.collection_end ?? ""} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, collection_end: event.target.value || null })} /></label>
              <label className="wide-field"><span>Summary (Markdown)</span><textarea rows={3} value={evidenceDraft.summary} onChange={(event) => setEvidenceDraft({ ...evidenceDraft, summary: event.target.value })} /></label>
              <label className="wide-field"><span>Collection decision</span><input maxLength={120} value={evidenceDecision} onChange={(event) => setEvidenceDecision(event.target.value)} /></label>
            </>}
            <div className="form-actions wide-field">
              <button type="button" className="primary-button" disabled={saving || (!existingEvidenceId && (!evidenceDraft.title || !evidenceDecision))} onClick={() => { void saveEvidence(); }}>{existingEvidenceId ? "Link evidence" : "Save evidence"}</button>
              <button type="button" className="secondary-button" onClick={() => setEvidenceFormOpen(false)}>{translate('common.cancel')}</button>
            </div>
          </div>
        )}
        {evidence.length === 0 ? <p className="empty-state">No evidence has been collected in this workspace.</p> : (
          <div className="network-table-wrap" role="group" aria-label={translate('compliance.evidenceTable')} tabIndex={0}><table className="network-table"><thead><tr><th>Evidence</th><th>Source / window</th><th>Controls</th><th>Latest review</th></tr></thead><tbody>{evidence.map((item) => <tr key={item.id}><td><strong>{item.title}</strong><small>{item.kind}</small></td><td>{item.source_url ? <a href={item.source_url} target="_blank" rel="noreferrer">Open source</a> : item.source_entity_name ?? "Recorded in TekDocs"}<small>{item.collection_start ?? "Open"} – {item.collection_end ?? "Open"}</small></td><td>{item.control_links.length ? item.control_links.map((link) => `r${link.control_revision}`).join(", ") : "Unlinked"}</td><td>{item.reviews[0] ? <><strong>{item.reviews[0].status}</strong><small>{item.reviews[0].decision}</small></> : "Not reviewed"}</td></tr>)}</tbody></table></div>
        )}
      </section>
      <section className="content-section compliance-risks" aria-labelledby="compliance-risks-heading">
        <div className="section-heading">
          <div>
            <h2 id="compliance-risks-heading">Risk register</h2>
            <p>Workspace risks with consistent scoring, accountable treatment, deadlines, and retained decisions.</p>
          </div>
          {canManage && <button type="button" className="secondary-button" onClick={() => { setEditingRiskId(null); setRiskDraft(EMPTY_RISK); setRiskFormOpen(true); }}><Plus size={15} /> {translate('compliance.addRisk')}</button>}
        </div>
        <div className="compliance-risk-summary" aria-label="Risk reporting summary">
          <span><strong>{riskSummary.total}</strong> total</span>
          <span><strong>{riskSummary.by_band.critical ?? 0}</strong> critical</span>
          <span><strong>{riskSummary.by_band.high ?? 0}</strong> high</span>
          <span><strong>{riskSummary.overdue}</strong> overdue</span>
        </div>
        {riskFormOpen && <div className="compliance-risk-form">
          <label className="wide-field"><span>Risk title</span><input value={riskDraft.title} maxLength={240} onChange={(event) => setRiskDraft({ ...riskDraft, title: event.target.value })} /></label>
          <label className="wide-field"><span>Description (Markdown)</span><textarea rows={3} value={riskDraft.description} onChange={(event) => setRiskDraft({ ...riskDraft, description: event.target.value })} /></label>
          <label><span>Likelihood (1–5)</span><input type="number" min={1} max={5} value={riskDraft.likelihood} onChange={(event) => setRiskDraft({ ...riskDraft, likelihood: Number(event.target.value) })} /></label>
          <label><span>Impact (1–5)</span><input type="number" min={1} max={5} value={riskDraft.impact} onChange={(event) => setRiskDraft({ ...riskDraft, impact: Number(event.target.value) })} /></label>
          <label><span>Status</span><select value={riskDraft.status} onChange={(event) => setRiskDraft({ ...riskDraft, status: event.target.value as ComplianceRiskDraft["status"], treatment: event.target.value === "accepted" ? "accept" : riskDraft.treatment === "accept" ? "mitigate" : riskDraft.treatment })}><option value="open">Open</option><option value="monitoring">Monitoring</option><option value="accepted">Accepted</option><option value="closed">Closed</option></select></label>
          <label><span>Treatment</span><select value={riskDraft.treatment} onChange={(event) => setRiskDraft({ ...riskDraft, treatment: event.target.value as ComplianceRiskDraft["treatment"], status: event.target.value === "accept" ? "accepted" : riskDraft.status === "accepted" ? "open" : riskDraft.status })}><option value="mitigate">Mitigate</option><option value="avoid">Avoid</option><option value="transfer">Transfer</option><option value="accept">Accept</option></select></label>
          <label><span>Owner</span><select value={riskDraft.owner_id ?? ""} onChange={(event) => setRiskDraft({ ...riskDraft, owner_id: event.target.value || null })}><option value="">Unassigned</option>{ownerChoices.map((owner) => <option key={owner.id} value={owner.id}>{owner.display_name}</option>)}</select></label>
          <label><span>Deadline</span><input type="date" value={riskDraft.due_date ?? ""} onChange={(event) => setRiskDraft({ ...riskDraft, due_date: event.target.value || null })} /></label>
          <label><span>Related control</span><select value={riskDraft.assignment_id ?? ""} onChange={(event) => setRiskDraft({ ...riskDraft, assignment_id: event.target.value || null })}><option value="">No direct control</option>{assignments.map((assignment) => <option key={assignment.id} value={assignment.id}>{assignment.control_identifier} — {assignment.control_title}</option>)}</select></label>
          <label className="wide-field"><span>Treatment plan (Markdown)</span><textarea rows={3} value={riskDraft.treatment_plan} onChange={(event) => setRiskDraft({ ...riskDraft, treatment_plan: event.target.value })} /></label>
          <label className="wide-field"><span>Decision</span><input maxLength={120} value={riskDraft.decision} onChange={(event) => setRiskDraft({ ...riskDraft, decision: event.target.value })} /></label>
          <label className="wide-field"><span>Review note</span><textarea rows={2} value={riskDraft.note} onChange={(event) => setRiskDraft({ ...riskDraft, note: event.target.value })} /></label>
          {riskDraft.status === "accepted" && <p className="form-note wide-field">Saving records you as the accepting actor. Acceptance is a retained decision, not deletion or remediation.</p>}
          <div className="form-actions wide-field"><button type="button" className="primary-button" disabled={saving || !riskDraft.title || !riskDraft.decision} onClick={() => { void saveRisk(); }}>{editingRiskId ? "Save review" : "Add risk"}</button><button type="button" className="secondary-button" onClick={() => setRiskFormOpen(false)}>{translate('common.cancel')}</button></div>
        </div>}
        {risks.length === 0 ? <p className="empty-state">No risks have been recorded in this workspace.</p> : <div className="network-table-wrap" role="group" aria-label={translate('compliance.riskTable')} tabIndex={0}><table className="network-table"><thead><tr><th>Risk</th><th>Score</th><th>Treatment</th><th>Owner / deadline</th><th>History</th></tr></thead><tbody>{risks.map((risk) => <tr key={risk.id}><td><strong>{risk.title}</strong><small>{risk.control ?? "General workspace risk"}</small></td><td><strong>{risk.score} · {risk.reporting_band}</strong><small>L{risk.likelihood} × I{risk.impact}</small></td><td><strong>{risk.status}</strong><small>{risk.treatment}</small></td><td>{risk.owner ?? "Unassigned"}<small>{risk.due_date ?? "No deadline"}</small></td><td><button type="button" className="text-button" onClick={() => editRisk(risk)}>{translate('common.review')}</button><small>{risk.events.length} retained decision{risk.events.length === 1 ? "" : "s"}</small></td></tr>)}</tbody></table></div>}
      </section>
      <section className="content-section compliance-risks" aria-labelledby="compliance-bundles-heading">
        <div className="section-heading"><div><h2 id="compliance-bundles-heading">Evidence bundles</h2><p>Immutable signed snapshots of the current controls, evidence, and risks.</p></div>{canManage && <button type="button" className="secondary-button" disabled={saving} onClick={() => { void (async () => { setSaving(true); try { const created = await client.createBundle(workspace, { title: `Compliance evidence ${new Date().toLocaleDateString()}`, reason: "Point-in-time compliance review", audience: "msp_internal" }); setBundles((current) => [created, ...current]); } catch (caught) { setError(caught instanceof Error ? caught.message : "The evidence bundle could not be created."); } finally { setSaving(false); } })(); }}>{translate('compliance.createSignedBundle')}</button>}</div>
        {bundles.length === 0 ? <p className="empty-state">No signed evidence bundles have been created.</p> : <div className="network-table-wrap" role="group" aria-label={translate('compliance.bundleTable')} tabIndex={0}><table className="network-table"><thead><tr><th>Bundle</th><th>Audience</th><th>Integrity</th><th>Created</th></tr></thead><tbody>{bundles.map((bundle) => <tr key={bundle.id}><td><strong>{bundle.title}</strong><small>{bundle.reason}</small></td><td>{bundle.audience.replace("_", " ")}</td><td><strong>{bundle.verified ? "Verified" : "Verification failed"}</strong><small>SHA-256 {bundle.content_digest.slice(0, 12)}</small></td><td>{new Date(bundle.created_at).toLocaleString()}<small>{bundle.created_by}</small></td></tr>)}</tbody></table></div>}
      </section>
      <DataFlows workspace={workspace} client={dataFlowClient} />
    </>
  );
}
