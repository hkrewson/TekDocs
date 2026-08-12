import { useEffect, useMemo, useState } from "react";
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
  ComplianceFramework,
  ComplianceFrameworkDraft,
  ComplianceOwnerChoice,
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
          Add control
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
          Cancel
        </button>
      </div>
    </>
  );
}

export function Compliance({
  workspace,
  client,
}: {
  workspace: WorkspaceContext | null;
  client: ComplianceClient;
}) {
  const [frameworks, setFrameworks] = useState<ComplianceFramework[]>([]);
  const [canManage, setCanManage] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [revisions, setRevisions] = useState<ComplianceCatalogRevision[]>([]);
  const [assignments, setAssignments] = useState<ComplianceAssignment[]>([]);
  const [ownerChoices, setOwnerChoices] = useState<ComplianceOwnerChoice[]>([]);
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
          <button type="button" className="primary-button" onClick={startNew}>
            <Plus size={16} />
            New framework
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
                    New version
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
                            Review control
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
                                Save review
                              </button>
                              <button
                                type="button"
                                className="secondary-button"
                                onClick={() => setReviewingControl(null)}
                              >
                                Cancel
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
    </>
  );
}
