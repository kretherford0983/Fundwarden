import { useEffect, useState, type FormEvent } from "react";
import { api, money, qs } from "../api";
import { ErrorBox, Field, Loading, Modal, GuardedForm } from "../components";
import { useMe } from "../App";
import { useRouter } from "../router";
import { BudgetSection } from "./BudgetTable";

export default function Budgets() {
  const { can } = useMe();
  const { search } = useRouter();
  const [fys, setFys] = useState<any[] | null>(null);
  const [fyId, setFyId] = useState<number | null>(null);
  const [tree, setTree] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [modal, setModal] = useState<any>(null);
  useEffect(() => {
    api.get("/api/fiscal-years").then((l: any[]) => {
      setFys(l);
      const want = Number(new URLSearchParams(search).get("fiscal_year_id"));
      const today = new Date().toISOString().slice(0, 10);
      const cur = l.find((f) => f.id === want) || l.find((f) => f.start_date <= today && f.end_date >= today && f.status !== "CLOSED") || l[l.length - 1];
      setFyId(cur ? cur.id : null);
    }, setErr);
  }, []);
  const load = () => fyId && api.get(`/api/budgets${qs({ fiscal_year_id: fyId })}`).then(setTree, setErr);
  useEffect(() => {
    setTree(null);
    load();
  }, [fyId]);
  if (!fys) return <><ErrorBox error={err} /><Loading /></>;
  const manage = can("budget.manage");
  const fy = fys.find((f) => f.id === fyId);
  const actions = manage ? {
    onEdit: (r: any) => setModal({ kind: "edit", row: r }),
    onAddChild: (r: any) => setModal({ kind: "create", parent: r }),
    onReject: (r: any) => setModal({ kind: "reason", row: r, action: "reject", title: `Reject ${r.label}` }),
    onInactivate: (r: any) => setModal({ kind: "reason", row: r, action: "inactivate", title: `Inactivate ${r.label}` }),
    onUnlock: (r: any) => setModal({ kind: "reason", row: r, action: "unlock", title: `Unlock ${r.label}` }),
    onLock: async (r: any) => { try { await api.post(`/api/budgets/${r.id}/lock`); load(); } catch (e) { setErr(e); } },
  } : undefined;
  const done = () => { setModal(null); load(); };
  return (
    <div>
      <div className="page-head">
        <h1>Budgets</h1>
        <Field label="Fiscal Year">
          <select aria-label="Budget Fiscal Year filter" value={fyId ?? ""} onChange={(e) => setFyId(Number(e.target.value))}>
            {fys.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
          </select>
        </Field>
        {manage && fy && fy.status !== "CLOSED" ? <button className="primary" onClick={() => setModal({ kind: "create" })}>New budget</button> : null}
      </div>
      <ErrorBox error={err} />
      {!fys.length ? <p className="muted">No Fiscal Years exist yet.</p> : null}
      {fy?.status === "CLOSED" ? <div className="alert info">{fy.display_name} is closed; budgets are read-only.</div> : null}
      {tree ? (
        <>
          <BudgetSection title="Income" rows={tree.income} summary={tree.income_summary} fyStatus={fy.status} actions={actions} registerLinks onHistory={(r) => setModal({ kind: "history", row: r })} />
          <BudgetSection title="Expense" rows={tree.expense} summary={tree.expense_summary} fyStatus={fy.status} actions={actions} registerLinks onHistory={(r) => setModal({ kind: "history", row: r })} />
          {tree.budget_zero ? (
            <p className="muted">Protected Budget 0 (non-budget activity such as transfers): inflows {money(tree.budget_zero.inflow)} · outflows {money(tree.budget_zero.outflow)}</p>
          ) : null}
        </>
      ) : fyId ? <Loading /> : null}
      {modal?.kind === "create" ? <BudgetForm fys={fys} fyId={fyId!} parent={modal.parent} onClose={() => setModal(null)} onSaved={done} /> : null}
      {modal?.kind === "edit" ? <BudgetEdit row={modal.row} canDelete={can("budget.delete") && fy?.status === "DRAFT"} onDelete={() => setModal({ kind: "reason", row: modal.row, action: "delete", title: `Delete ${modal.row.label}` })} onClose={() => setModal(null)} onSaved={done} /> : null}
      {modal?.kind === "history" ? <BudgetHistory row={modal.row} onClose={() => setModal(null)} /> : null}
      {modal?.kind === "reason" ? <ReasonForm {...modal} onClose={() => setModal(null)} onSaved={done} /> : null}
    </div>
  );
}

function BudgetForm({ fys, fyId, parent, onClose, onSaved }: any) {
  const [f, setF] = useState({ fiscal_year_id: fyId, code: "", name: "", budget_type: parent?.budget_type || "EXPENSE", amount: "", notes: "" });
  const [cont, setCont] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.post("/api/budgets", {
        fiscal_year_id: Number(f.fiscal_year_id), code: f.code, name: f.name, amount: f.amount, notes: f.notes || null,
        continues_budget_id: cont ? Number(cont) : null,
        ...(parent ? { parent_budget_id: parent.id } : { budget_type: f.budget_type }),
      });
      onSaved();
    } catch (x) { setErr(x); }
  };
  return (
    <Modal title={parent ? `New sub-budget of ${parent.label}` : "New budget"} onClose={onClose}>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        {!parent ? (
          <Field label="Fiscal Year">
            <select aria-label="Create Budget Fiscal Year" value={f.fiscal_year_id} onChange={(e) => setF({ ...f, fiscal_year_id: Number(e.target.value) })}>
              {fys.filter((x: any) => x.status !== "CLOSED").map((x: any) => <option key={x.id} value={x.id}>{x.label}</option>)}
            </select>
          </Field>
        ) : <p>Parent: <b>{parent.label}</b> · Other currently {money(parent.other_amount)}</p>}
        <Field label={parent ? "Sub-budget code (e.g. 01)" : "Budget code (e.g. 1000)"}><input required pattern="[A-Za-z0-9]{1,10}" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} /></Field>
        <Field label="Name"><input required maxLength={120} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        {!parent ? (
          <Field label="Type"><select value={f.budget_type} onChange={(e) => setF({ ...f, budget_type: e.target.value })}><option value="INCOME">Income</option><option value="EXPENSE">Expense</option></select></Field>
        ) : null}
        <Field label="Amount"><input required inputMode="decimal" pattern="\d+(\.\d{1,2})?" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
        <ContinuesField fyId={Number(f.fiscal_year_id)} budgetType={f.budget_type} subBudget={!!parent} value={cont} onChange={setCont} />
        <Field label="Notes"><textarea value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
        <div className="actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" type="submit">Create</button></div>
      </GuardedForm>
    </Modal>
  );
}

function BudgetEdit({ row, onClose, onSaved, canDelete, onDelete }: any) {
  const [f, setF] = useState({ name: row.name, amount: row.amount, notes: row.notes || "" });
  const [cont, setCont] = useState(row.continues_budget_id ? String(row.continues_budget_id) : "");
  const [err, setErr] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.patch(`/api/budgets/${row.id}`, { name: f.name, amount: f.amount, notes: f.notes || null,
                                                continues_budget_id: cont ? Number(cont) : null });
      onSaved();
    } catch (x) { setErr(x); }
  };
  return (
    <Modal title={`Edit ${row.label}`} onClose={onClose}>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        <Field label="Name"><input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Amount" hint="Other is recalculated automatically; sub-budgets may not exceed the parent."><input required value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
        <ContinuesField fyId={row.fiscal_year_id} budgetType={row.budget_type} subBudget={!!row.parent_budget_id} budgetId={row.id} value={cont} onChange={setCont} />
        <Field label="Notes"><textarea value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
        <div className="actions">
          {/* 1.7.3 (#52): Budget Admins - red, set apart from Save / Cancel */}
          {canDelete && !row.system_managed ? <button type="button" className="danger delete-apart" onClick={onDelete}>Delete budget…</button> : null}
          <button type="button" onClick={onClose}>Cancel</button><button className="primary" type="submit">Save</button>
        </div>
      </GuardedForm>
    </Modal>
  );
}

function ReasonForm({ row, action, title, onClose, onSaved }: any) {
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.post(`/api/budgets/${row.id}/${action}`, { reason });
      onSaved();
    } catch (x) { setErr(x); }
  };
  return (
    <Modal title={title} onClose={onClose}>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        {action === "reject" ? <p>A rejected budget's allowed amount becomes 0. Existing allocations are preserved.</p> : null}
        {action === "unlock" ? <p>Unlocking permits an authorized amendment and is audited.</p> : null}
        {action === "delete" ? (
          <div className="alert warn" role="alert">
            <b>The budget will be deleted.</b> It disappears from the Budgets page, the budget lists and the totals, and
            it will not be copied into a new Fiscal Year. Auditors can still see it, with your reason. This cannot be
            undone. A budget with Register allocations or sub-budgets cannot be deleted.
          </div>
        ) : null}
        <Field label="Reason (required)"><textarea required value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="actions"><button type="button" onClick={onClose}>Cancel</button><button className={`primary${action === "delete" ? " danger" : ""}`} type="submit" disabled={!reason.trim()}>{action === "delete" ? "Delete budget" : "Confirm"}</button></div>
      </GuardedForm>
    </Modal>
  );
}

/** 1.8.0 (#89): the earlier budget this one continues - budgets of earlier Fiscal Years, same type and level,
 * not already continued by another budget; grouped by Fiscal Year, newest first. */
function ContinuesField({ fyId, budgetType, subBudget, budgetId, value, onChange }: {
  fyId: number; budgetType: string; subBudget: boolean; budgetId?: number; value: string; onChange: (v: string) => void;
}) {
  const [groups, setGroups] = useState<any[] | null>(null);
  useEffect(() => {
    setGroups(null);
    api.get(`/api/budgets/continue-options${qs({ fiscal_year_id: fyId, budget_type: budgetType, level: subBudget ? "sub-budget" : "budget", budget_id: budgetId })}`)
      .then((g: any[]) => {
        setGroups(g);
        if (value && !g.some((x) => x.options.some((o: any) => String(o.id) === value))) onChange("");
      }, () => setGroups([]));
  }, [fyId, budgetType, subBudget, budgetId]);
  if (groups && !groups.length) return null; // nothing earlier to continue
  return (
    <Field label="Continues" hint={subBudget ? "The sub-budget of an earlier Fiscal Year that this sub-budget continues (optional)."
      : "The budget of an earlier Fiscal Year that this budget continues (optional). History then shows them together."}>
      <select aria-label="Continues budget" value={value} onChange={(e) => onChange(e.target.value)} disabled={groups === null}>
        <option value="">— None —</option>
        {(groups || []).map((g) => (
          <optgroup key={g.fiscal_year.id} label={g.fiscal_year.display_name}>
            {g.options.map((o: any) => <option key={o.id} value={o.id}>{o.label}</option>)}
          </optgroup>
        ))}
      </select>
    </Field>
  );
}

/** 1.8.0 (#89): the budget's lineage across Fiscal Years, oldest first. */
function BudgetHistory({ row, onClose }: any) {
  const [h, setH] = useState<any[] | null>(null);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => { api.get(`/api/budgets/${row.id}/history`).then(setH, setErr); }, [row.id]);
  return (
    <Modal title={`History of ${row.label}`} onClose={onClose}>
      <ErrorBox error={err} />
      {!h ? (err ? null : <Loading />) : (
        <div className="table-wrap">
          <table className="table" aria-label="Budget history">
            <thead><tr><th>Fiscal Year</th><th>ID</th><th>Name</th><th className="num">Amount</th><th className="num">Actual</th></tr></thead>
            <tbody>
              {h.map((x) => (
                <tr key={x.id} className={x.this ? "current-row" : ""} aria-current={x.this ? "true" : undefined}>
                  <td>{x.fiscal_year.display_name}</td><td><span className="code">{x.code}</span></td>
                  <td>{x.this ? <b>{x.name}</b> : x.name}{["REJECTED", "INACTIVE"].includes(x.status) ? <span className="muted"> ({x.status.toLowerCase()})</span> : null}</td>
                  <td className="num">{money(x.amount)}</td><td className="num">{money(x.actual)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="actions"><button type="button" onClick={onClose}>Close</button></div>
    </Modal>
  );
}
