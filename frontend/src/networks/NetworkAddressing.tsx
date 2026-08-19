import { useEffect, useMemo, useState } from "react";
import { translate } from '../i18n/localization'
import type { FormEvent } from "react";
import { Pencil, Plus } from "lucide-react";
import type { WorkspaceContext } from "../workspaces/api";
import type {
  NetworkSubnet,
  NetworkVLAN,
  NetworkVRF,
  NetworksClient,
  SubnetWrite,
  VLANWrite,
  VRFWrite,
} from "./api";

type Kind = "subnets" | "vlans" | "vrfs";
type FormState = {
  kind: Kind;
  id: string | null;
  values: SubnetWrite | VLANWrite | VRFWrite;
};
const blank = (kind: Kind): FormState =>
  kind === "subnets"
    ? {
        kind,
        id: null,
        values: {
          name: "",
          cidr: "",
          vrf_id: null,
          vlan_id: null,
          description: "",
        },
      }
    : kind === "vlans"
      ? { kind, id: null, values: { name: "", vlan_id: 1, description: "" } }
      : {
          kind,
          id: null,
          values: { name: "", route_distinguisher: "", description: "" },
        };
const message = (error: unknown) =>
  error instanceof Error ? error.message : "The addressing request failed.";

export function NetworkAddressing({
  workspace,
  client,
  kind,
  query,
}: {
  workspace: WorkspaceContext;
  client: NetworksClient;
  kind: Kind;
  query: string;
}) {
  const [vrfs, setVRFs] = useState<NetworkVRF[] | null>(null);
  const [vlans, setVLANs] = useState<NetworkVLAN[] | null>(null);
  const [subnets, setSubnets] = useState<NetworkSubnet[] | null>(null);
  const [canManage, setCanManage] = useState(false);
  const [form, setForm] = useState<FormState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) {
        setVRFs(null);
        setVLANs(null);
        setSubnets(null);
        setError(null);
        setForm(null);
      }
    });
    Promise.all([
      client.listVRFs(workspace, controller.signal),
      client.listVLANs(workspace, controller.signal),
      client.listSubnets(workspace, controller.signal),
    ])
      .then(([vrfResult, vlanResult, subnetResult]) => {
        setVRFs(vrfResult.results);
        setVLANs(vlanResult.results);
        setSubnets(subnetResult.results);
        setCanManage(subnetResult.can_manage);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(message(caught));
      });
    return () => controller.abort();
  }, [client, workspace]);

  const normalized = query.toLowerCase();
  const shownVRFs = useMemo(
    () =>
      (vrfs ?? []).filter((item) =>
        `${item.name} ${item.route_distinguisher} ${item.description}`
          .toLowerCase()
          .includes(normalized),
      ),
    [normalized, vrfs],
  );
  const shownVLANs = useMemo(
    () =>
      (vlans ?? []).filter((item) =>
        `${item.name} ${item.vlan_id} ${item.description}`
          .toLowerCase()
          .includes(normalized),
      ),
    [normalized, vlans],
  );
  const shownSubnets = useMemo(
    () =>
      (subnets ?? []).filter((item) =>
        `${item.name} ${item.cidr} ${item.vrf_name ?? ""} ${item.vlan_number ?? ""}`
          .toLowerCase()
          .includes(normalized),
      ),
    [normalized, subnets],
  );

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!form) return;
    setBusy(true);
    setError(null);
    try {
      if (form.kind === "vrfs") {
        const values = form.values as VRFWrite;
        const saved = form.id
          ? await client.updateVRF(workspace, form.id, values)
          : await client.createVRF(workspace, values);
        setVRFs((items) =>
          form.id
            ? (items ?? []).map((item) => (item.id === saved.id ? saved : item))
            : [...(items ?? []), saved],
        );
      } else if (form.kind === "vlans") {
        const values = form.values as VLANWrite;
        const saved = form.id
          ? await client.updateVLAN(workspace, form.id, values)
          : await client.createVLAN(workspace, values);
        setVLANs((items) =>
          form.id
            ? (items ?? []).map((item) => (item.id === saved.id ? saved : item))
            : [...(items ?? []), saved],
        );
      } else {
        const values = form.values as SubnetWrite;
        const saved = form.id
          ? await client.updateSubnet(workspace, form.id, values)
          : await client.createSubnet(workspace, values);
        setSubnets((items) =>
          form.id
            ? (items ?? []).map((item) => (item.id === saved.id ? saved : item))
            : [...(items ?? []), saved],
        );
      }
      setForm(null);
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(false);
    }
  }

  function edit(item: NetworkVRF | NetworkVLAN | NetworkSubnet) {
    if (kind === "vrfs") {
      const value = item as NetworkVRF;
      setForm({
        kind,
        id: value.id,
        values: {
          name: value.name,
          route_distinguisher: value.route_distinguisher,
          description: value.description,
        },
      });
    } else if (kind === "vlans") {
      const value = item as NetworkVLAN;
      setForm({
        kind,
        id: value.id,
        values: {
          name: value.name,
          vlan_id: value.vlan_id,
          description: value.description,
        },
      });
    } else {
      const value = item as NetworkSubnet;
      setForm({
        kind,
        id: value.id,
        values: {
          name: value.name,
          cidr: value.cidr,
          vrf_id: value.vrf_id,
          vlan_id: value.vlan_id,
          description: value.description,
        },
      });
    }
  }

  const loading = vrfs === null || vlans === null || subnets === null;
  return (
    <>
      <div className="network-addressing-actions">
        {canManage && (
          <button
            className="primary-button"
            type="button"
            onClick={() => setForm(blank(kind))}
          >
            <Plus size={15} />
            Add {kind === "vrfs" ? "VRF" : kind === "vlans" ? "VLAN" : "subnet"}
          </button>
        )}
      </div>
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      {form && (
        <form className="network-form" onSubmit={(event) => void save(event)}>
          <h2>
            {form.id ? "Edit" : "Add"}{" "}
            {form.kind === "vrfs"
              ? "VRF"
              : form.kind === "vlans"
                ? "VLAN"
                : "subnet"}
          </h2>
          <div className="field-grid">
            <label>
              <span>Name</span>
              <input
                required
                value={form.values.name}
                onChange={(event) =>
                  setForm({
                    ...form,
                    values: { ...form.values, name: event.target.value },
                  })
                }
              />
            </label>
            {form.kind === "vrfs" && (
              <label>
                <span>Route distinguisher</span>
                <input
                  value={(form.values as VRFWrite).route_distinguisher}
                  placeholder="Optional, for example 65000:10"
                  onChange={(event) =>
                    setForm({
                      ...form,
                      values: {
                        ...form.values,
                        route_distinguisher: event.target.value,
                      },
                    })
                  }
                />
              </label>
            )}
            {form.kind === "vlans" && (
              <label>
                <span>VLAN ID</span>
                <input
                  type="number"
                  min="1"
                  max="4094"
                  required
                  value={(form.values as VLANWrite).vlan_id}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      values: {
                        ...form.values,
                        vlan_id: Number(event.target.value),
                      },
                    })
                  }
                />
              </label>
            )}
            {form.kind === "subnets" && (
              <>
                <label>
                  <span>CIDR</span>
                  <input
                    required
                    value={(form.values as SubnetWrite).cidr}
                    placeholder="192.0.2.0/24"
                    onChange={(event) =>
                      setForm({
                        ...form,
                        values: { ...form.values, cidr: event.target.value },
                      })
                    }
                  />
                  <small>Use the network address, not a host address.</small>
                </label>
                {(form.values as SubnetWrite).vrf_id && (
                  <p className="field-note">
                    This retained subnet uses a legacy VRF. Its routing assignment is preserved but managed in NetBox.
                  </p>
                )}
                <label>
                  <span>VLAN</span>
                  <select
                    value={(form.values as SubnetWrite).vlan_id ?? ""}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        values: {
                          ...(form.values as SubnetWrite),
                          vlan_id: event.target.value || null,
                        } as SubnetWrite,
                      })
                    }
                  >
                    <option value="">No VLAN</option>
                    {(vlans ?? []).map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.vlan_id} · {item.name}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
            <label className="field-wide">
              <span>Description</span>
              <textarea
                rows={3}
                value={form.values.description}
                onChange={(event) =>
                  setForm({
                    ...form,
                    values: { ...form.values, description: event.target.value },
                  })
                }
              />
            </label>
          </div>
          <div className="form-actions">
            <button className="primary-button" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() => setForm(null)}
            >
              {translate('common.cancel')}
            </button>
          </div>
        </form>
      )}
      {loading ? (
        <p role="status">Loading network addressing…</p>
      ) : kind === "vrfs" ? (
        <Table
          headers={["Name", "Route distinguisher", "Description"]}
          items={shownVRFs}
          row={(item) => [
            item.name,
            item.route_distinguisher || "—",
            item.description || "—",
          ]}
          onEdit={canManage ? edit : undefined}
          empty="No VRFs match this workspace and search."
        />
      ) : kind === "vlans" ? (
        <Table
          headers={["VLAN", "Name", "Description"]}
          items={shownVLANs}
          row={(item) => [
            String(item.vlan_id),
            item.name,
            item.description || "—",
          ]}
          onEdit={canManage ? edit : undefined}
          empty="No VLANs match this workspace and search."
        />
      ) : (
        <Table
          headers={["Name", "CIDR", "Family", "Legacy routing", "VLAN"]}
          items={shownSubnets}
          row={(item) => [
            item.name,
            item.cidr,
            `IPv${item.address_family}`,
            item.vrf_name ? `Legacy VRF: ${item.vrf_name}` : "Default",
            item.vlan_number ? `${item.vlan_number} · ${item.vlan_name}` : "—",
          ]}
          onEdit={canManage ? edit : undefined}
          empty="No subnets match this workspace and search."
        />
      )}
    </>
  );
}

function Table<T extends { id: string }>({
  headers,
  items,
  row,
  onEdit,
  empty,
}: {
  headers: string[];
  items: T[];
  row: (item: T) => string[];
  onEdit?: (item: T) => void;
  empty: string;
}) {
  return (
    <div className="network-table-wrap">
      <table className="network-table">
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
            <th>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              {row(item).map((cell, index) => (
                <td key={`${item.id}-${headers[index]}`}>
                  {index === 0 ? <strong>{cell}</strong> : cell}
                </td>
              ))}
              <td>
                {onEdit && (
                  <button
                    className="row-action"
                    type="button"
                    onClick={() => onEdit(item)}
                  >
                    <Pencil size={14} />
                    {translate('common.edit')}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {items.length === 0 && <p className="empty-state">{empty}</p>}
    </div>
  );
}
