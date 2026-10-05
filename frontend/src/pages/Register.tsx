import { Fragment, useEffect, useRef, useState, type FormEvent } from "react";
import { api, money, newRequestKey, qs, todayIso } from "../api";
import { allocationLabel, Attachments, EntityPicker, ErrorBox, Field, Loading, Modal, PendingFiles, useConfirmable, GuardedForm } from "../components";
import { useMe } from "../App";
import { EntityForm } from "./Entities";

export default function Register() {
  const { can } = useMe();
  const [accounts, setAccounts] = useState<any[] | null>(null);
  const [fys, setFys] = useState<any[]>([]);
  const [f, setF] = useState({ bank_account_id: "", fiscal_year_id: "", transaction_type: "", status: "", date_from: "", date_to: "", search: "", attachments: "" });
  const [defaultFy, setDefaultFy] = useState(""); // 1.6.7: what "Clear" goes back to (the current Fiscal Year)
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [modal, setModal] = useState<any>(null);
  const [showReviews, setShowReviews] = useState(new URLSearchParams(window.location.search).has("reviews"));
  const manage = can("transaction.manage");
  // CR-015: the pinned header's height positions the pinned table headings directly below it
  const stickyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = stickyRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => el.parentElement?.style.setProperty("--register-sticky-h", `${el.offsetHeight}px`));
    ro.observe(el);
    return () => ro.disconnect();
  });

  useEffect(() => {
    Promise.all([api.get("/api/bank-accounts"), api.get("/api/fiscal-years"), api.get(`/api/fiscal-years/natural?date=${todayIso()}`)]).then(([a, y, nat]) => {
      const reg = a.filter((x: any) => x.register_enabled);
      setAccounts(reg);
      setFys(y);
      const primary = reg.find((x: any) => x.is_primary) || reg.find((x: any) => x.status === "ACTIVE") || reg[0];
      // v1.6.0: deep link from a fundraiser line - /register?account=<id>&search=<text> (all dates)
      setDefaultFy(nat.default_fiscal_year_id ? String(nat.default_fiscal_year_id) : "");
      const q = new URLSearchParams(window.location.search);
      const linked = reg.find((x: any) => String(x.id) === q.get("account"));
      if (linked) setF((p) => ({ ...p, bank_account_id: String(linked.id), fiscal_year_id: "", search: q.get("search") || "" }));
      else setF((p) => ({ ...p, bank_account_id: primary ? String(primary.id) : "", fiscal_year_id: nat.default_fiscal_year_id ? String(nat.default_fiscal_year_id) : "" }));
    }, setErr);
  }, []);
  const load = () => {
    if (!f.bank_account_id) return;
    api.get(`/api/register${qs(f)}`).then(setData, setErr);
  };
  useEffect(() => { load(); }, [f]);
  if (!accounts) return <><ErrorBox error={err} /><Loading /></>;
  const acct = data?.bank_account;
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  // 1.6.7: "Clear" puts every filter back to how the register opens; the chosen bank account stays
  const defaults = { fiscal_year_id: defaultFy, transaction_type: "", status: "", date_from: "", date_to: "", search: "", attachments: "" };
  const filtered = (Object.keys(defaults) as (keyof typeof defaults)[]).some((k) => f[k] !== defaults[k]);
  return (
    <div className="register-page">
      <div className="register-sticky" ref={stickyRef}>
      <div className="page-head">
        <h1>Register</h1>
        <Field label="Bank account">
          <select aria-label="Register bank account" value={f.bank_account_id} onChange={set("bank_account_id")}>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.label}{a.status === "CLOSED" ? " (closed)" : ""}</option>)}
          </select>
        </Field>
        {manage && acct?.status === "ACTIVE" ? (
          <>
            <button className="primary" onClick={() => setModal({ kind: "txn", txn: null })}>New transaction</button>
            <button onClick={() => setModal({ kind: "transfer" })}>Transfer…</button>
            <button onClick={() => setModal({ kind: "zero" })}>Zero-dollar VOID record</button>
          </>
        ) : null}
        <button onClick={() => setShowReviews(!showReviews)} aria-expanded={showReviews}>Fiscal Year reviews</button>
      </div>
      {!accounts.length ? <p className="muted">No register-enabled bank accounts.</p> : null}
      <div className="filters">
        <Field label="Fiscal Year (date filter)">
          <select aria-label="Register Fiscal Year filter" value={f.fiscal_year_id} onChange={set("fiscal_year_id")}>
            <option value="">All dates (continuous register)</option>
            {fys.map((y) => <option key={y.id} value={y.id}>{y.label}</option>)}
          </select>
        </Field>
        <Field label="Type"><select value={f.transaction_type} onChange={set("transaction_type")}><option value="">All</option><option value="DEPOSIT">Deposits</option><option value="WITHDRAWAL">Withdrawals</option></select></Field>
        <Field label="Status"><select value={f.status} onChange={set("status")}><option value="">All</option><option value="cleared">Cleared</option><option value="uncleared">Uncleared</option><option value="void">Void</option></select></Field>
        <Field label="Attachments"><select value={f.attachments} onChange={set("attachments")}><option value="">All</option><option value="yes">Yes</option><option value="no">No</option></select></Field>
        <Field label="From"><input type="date" value={f.date_from} onChange={set("date_from")} /></Field>
        <Field label="To"><input type="date" value={f.date_to} onChange={set("date_to")} /></Field>
        <Field label="Search"><input value={f.search} onChange={set("search")} placeholder="Entity, description, invoice, check #, amount" /></Field>
        <button type="button" className="filters-clear" disabled={!filtered} onClick={() => setF({ ...f, ...defaults })}
                title="Reset the filters to how the register opens (the bank account stays)">Clear</button>
      </div>
      {data && acct ? (
        <div className="tiles">
          <div className="tile"><div className="tile-label">Starting balance{data.date_from ? ` (as of ${data.date_from})` : " (opening)"}</div><div className="tile-value">{money(data.starting_balance)}</div></div>
          <div className="tile"><div className="tile-label">Ending balance{data.date_to ? ` (${data.date_to})` : ""}</div><div className="tile-value">{money(data.ending_balance)}</div></div>
          <div className="tile"><div className="tile-label">Current balance</div><div className="tile-value">{money(data.current_balance)}</div></div>
        </div>
      ) : null}
      </div>
      <ErrorBox error={err} />
      {showReviews ? (
        <Reviews canResolve={can("review.resolve")} canManage={manage && acct?.status === "ACTIVE"} account={acct} reloadKey={data}
          onEnterCheck={(n) => setModal({ kind: "txn", txn: null, initial: { check_number: String(n) } })}
          onZeroCheck={(n) => setModal({ kind: "zero", initial: { check_number: String(n) } })}
          onChange={load} />
      ) : null}
      {data && acct ? (
        <>
          <div className="table-wrap">
            <table className="table register">
              <thead>
                <tr><th /><th>Date</th><th>Cleared</th><th>Entity</th><th>Check #</th><th>Invoice #</th><th>Description</th><th className="num">Deposit</th><th className="num">Withdrawal</th><th className="num">Balance</th><th>Status</th><th title="Attachments">📎</th></tr>
              </thead>
              <tbody>
                {data.transactions.length === 0 ? <tr><td colSpan={12} className="muted">No transactions match.</td></tr> : null}
                {data.transactions.map((t: any) => (
                  <Fragment key={t.id}>
                    <tr className={`${t.status === "VOID" ? "void" : ""} ${t.has_pending_review ? "review" : ""}`}>
                      <td><button className="small" aria-expanded={open === t.id} aria-label={`Details for transaction ${t.id}`} onClick={() => setOpen(open === t.id ? null : t.id)}>{open === t.id ? "▾" : "▸"}</button></td>
                      <td>{t.transaction_date}</td><td>{t.clear_date || ""}</td><td>{t.entity?.display_name || ""}</td><td>{t.check_number || ""}</td>
                      <td>{t.invoice_numbers.join(", ")}</td>
                      <td>{t.is_split ? `Split (${t.allocations.length})` : t.allocations[0]?.description || t.allocations[0]?.budget.label}</td>
                      <td className="num">{t.deposit ? money(t.deposit) : ""}</td><td className="num">{t.withdrawal ? money(t.withdrawal) : ""}</td>
                      <td className="num">{money(t.running_balance)}</td>
                      <td>{t.status === "VOID" ? <span className="badge red">VOID</span> : t.cleared ? "Cleared" : "Uncleared"}{t.has_pending_review ? <span className="badge yellow">Review</span> : null}{t.transfer ? <span className="badge blue">Transfer</span> : null}{t.no_attachment ? <span className="badge grey" title={t.no_attachment_reason || ""}>No attachment</span> : null}</td>
                      <td>{t.attachment_count ? <span aria-label={`${t.attachment_count} attachments`}>📎{t.attachment_count}</span> : ""}</td>
                    </tr>
                    {open === t.id ? (
                      <tr className="detail-row"><td colSpan={12}><TxnDetail t={t} manage={manage} onEdit={() => setModal({ kind: t.transfer ? "legedit" : "txn", txn: t })} onVoid={() => setModal({ kind: "void", txn: t })} onVoidDate={() => setModal({ kind: "voiddate", txn: t })} onVoidCheck={() => setModal({ kind: "voidcheck", txn: t })} onChanged={load} /></td></tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : f.bank_account_id ? <Loading /> : null}
      {modal?.kind === "txn" ? <TxnForm account={acct} txn={modal.txn} initial={modal.initial} fys={fys} onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); }} /> : null}
      {modal?.kind === "void" ? <VoidForm txn={modal.txn} onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); }} /> : null}
      {modal?.kind === "transfer" ? <TransferForm accounts={accounts} fromId={acct?.id} fys={fys} onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); }} /> : null}
      {modal?.kind === "legedit" ? <TransferLegForm txn={modal.txn} onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); }} /> : null}
      {modal?.kind === "voiddate" ? <VoidDateForm txn={modal.txn} fys={fys} onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); }} /> : null}
      {modal?.kind === "voidcheck" ? <VoidCheckForm txn={modal.txn} onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); }} /> : null}
      {modal?.kind === "zero" ? <ZeroVoidForm account={acct} initial={modal.initial} fys={fys} onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); }} /> : null}
    </div>
  );
}

function TxnDetail({ t, manage, onEdit, onVoid, onVoidDate, onVoidCheck, onChanged }: { t: any; manage: boolean; onEdit: () => void; onVoid: () => void; onVoidDate: () => void; onVoidCheck: () => void; onChanged: () => void }) {
  const [note, setNote] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const editable = manage && t.status === "ACTIVE" && !t.closed_fiscal_year_protected;
  const addNote = async (e: FormEvent) => {
    e.preventDefault();
    try { await api.post(`/api/transactions/${t.id}/notes`, { note }); setNote(""); onChanged(); } catch (x) { setErr(x); }
  };
  return (
    <div className="txn-detail">
      <ErrorBox error={err} />
      <dl className="dl">
        <dt>Transaction #</dt><dd>{t.id} · {t.transaction_type}</dd>
        <dt>Transaction date</dt><dd>{t.transaction_date}</dd>
        <dt>Entry timestamp</dt><dd>{t.entry_timestamp.replace("T", " ").slice(0, 19)} UTC (system)</dd>
        <dt>Clear/Post date</dt><dd>{t.clear_date || "Uncleared"}</dd>
        <dt>Total (derived)</dt><dd>{money(t.total)}</dd>
        {t.status === "VOID" ? <><dt>Void reason</dt><dd>{t.void_reason}</dd></> : null}
        {t.notes ? <><dt>Notes</dt><dd className="pre">{t.notes}</dd></> : null}
        {t.transfer ? <><dt>Transfer</dt><dd>{t.transfer.direction === "OUT" ? "To" : "From"} {t.transfer.counterpart_account?.label} (transaction #{t.transfer.counterpart_transaction_id}). Voiding either side voids both.</dd></> : null}
        {t.no_attachment ? <><dt>Documentation</dt><dd>No attachment will be provided{t.no_attachment_reason ? `: ${t.no_attachment_reason}` : ""}</dd></> : null}
        {t.closed_fiscal_year_protected ? <><dt>Protection</dt><dd>Affects a Closed Fiscal Year – financial fields are immutable.</dd></> : null}
      </dl>
      <table className="table compact">
        <thead><tr><th>Fiscal Year</th><th>Budget</th><th>Entity</th><th>Invoice #</th><th>Description</th><th className="num">Amount</th><th>Review</th><th>Notes</th><th>Docs</th></tr></thead>
        <tbody>
          {t.allocations.map((a: any) => (
            <tr key={a.id}>
              <td>{a.budget.fiscal_year.display_name}</td><td>{a.budget.label}{a.budget.status === "REJECTED" ? " (rejected)" : ""}</td>
              <td>{a.entity?.display_name || ""}</td><td>{a.invoice_number || ""}</td><td>{a.description || ""}</td>
              <td className="num">{money(a.amount)}</td>
              <td>{a.reviews.map((r: any) => `${r.category === "CROSS_FY" ? "Cross-FY" : "No FY"}: ${r.status}`).join("; ")}</td>
              <td>{a.notes || ""}</td>
              <td>{a.attachment_count ? `📎${a.attachment_count}` : a.no_attachment ? <span className="badge grey" title={a.no_attachment_reason || ""}>No attachment</span> : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="actions left">
        {editable ? <button onClick={onEdit}>Edit</button> : null}
        {editable ? <button className="danger" onClick={onVoid}>Void…</button> : null}
        {manage && t.status === "VOID" && !t.closed_fiscal_year_protected ? <button onClick={onVoidDate}>Correct date…</button> : null}
        {manage && t.status === "VOID" && t.transaction_type === "WITHDRAWAL" && !t.transfer && !t.closed_fiscal_year_protected ? <button onClick={onVoidCheck}>Correct check number…</button> : null}
      </div>
      <Attachments ownerType="transaction" ownerId={t.id} canUpload={manage} canRemove={editable} title="Transaction attachments" />
      {t.allocations.length > 1 ? t.allocations.map((a: any) => (
        <Attachments key={a.id} ownerType="allocation" ownerId={a.id} canUpload={manage} canRemove={editable} title={allocationLabel(t, a)} />
      )) : null}
      {manage ? (
        <GuardedForm onSubmit={addNote} className="row">
          <Field label="Add supporting note"><input required maxLength={4000} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <button type="submit">Add note</button>
        </GuardedForm>
      ) : null}
    </div>
  );
}

type Alloc = { id?: number; fiscal_year_id: string; budget_id: string; entity_id: string; invoice_number: string; description: string; amount: string; notes: string; no_attachment: boolean; no_attachment_reason: string; files: File[] };
const blankAlloc = (fy = ""): Alloc => ({ fiscal_year_id: fy, budget_id: "", entity_id: "", invoice_number: "", description: "", amount: "", notes: "", no_attachment: false, no_attachment_reason: "", files: [] });

function useBudgetOptions(fyIds: string[], type: string) {
  const [cache, setCache] = useState<Record<string, any[]>>({});
  const wanted = Array.from(new Set(fyIds.filter(Boolean))).map((fy) => `${fy}:${type}`);
  useEffect(() => {
    wanted.filter((k) => !(k in cache)).forEach((k) => {
      const [fy, t] = k.split(":");
      setCache((c) => ({ ...c, [k]: [] }));
      api.get(`/api/budgets/selectable${qs({ fiscal_year_id: fy, transaction_type: t })}`).then((o) => setCache((c) => ({ ...c, [k]: o })));
    });
  }, [wanted.join(",")]);
  return (fy: string, t: string) => cache[`${fy}:${t}`] || [];
}

function TxnForm({ account, txn, initial, fys, onClose, onSaved }: { account: any; txn: any; initial?: { check_number?: string }; fys: any[]; onClose: () => void; onSaved: () => void }) {
  const isNew = !txn;
  const [type, setType] = useState<string>(txn?.transaction_type || "WITHDRAWAL");
  const [h, setH] = useState({
    transaction_date: txn?.transaction_date || todayIso(), clear_date: txn?.clear_date || "",
    entity_id: txn?.entity && !txn.entity.is_system ? String(txn.entity.id) : "", check_number: txn?.check_number || initial?.check_number || "", notes: txn?.notes || "",
    no_attachment: !!txn?.no_attachment, no_attachment_reason: txn?.no_attachment_reason || "",
  });
  // null = closed, -1 = whole transaction, n = allocation n
  const [noAttDlg, setNoAttDlg] = useState<number | null>(null);
  const [allocs, setAllocs] = useState<Alloc[]>(txn ? txn.allocations.map((a: any) => ({
    id: a.id, fiscal_year_id: String(a.budget.fiscal_year.id), budget_id: String(a.budget.id), entity_id: a.entity ? String(a.entity.id) : "",
    invoice_number: a.invoice_number || "", description: a.description || "", amount: a.amount, notes: a.notes || "",
    no_attachment: !!a.no_attachment, no_attachment_reason: a.no_attachment_reason || "", files: [],
  })) : [blankAlloc()]);
  const [parentFiles, setParentFiles] = useState<File[]>([]);
  const [uploadIssues, setUploadIssues] = useState<null | { id: number; failed: string[] }>(null);
  const [split, setSplit] = useState(txn ? txn.allocations.length > 1 : false);
  const [nat, setNat] = useState<any>(null);
  const [entities, setEntities] = useState<any[]>([]);
  const [err, setErr] = useState<unknown>(null);
  const [typeDlg, setTypeDlg] = useState<string | null>(null);
  const [newEnt, setNewEnt] = useState(false);
  const { run, dialog } = useConfirmable();
  const requestKey = useRef(newRequestKey()).current; // CR-011: repeated submits of this form create one transaction
  const loadEntities = () => api.get("/api/entities?status=active").then(setEntities);
  useEffect(() => { loadEntities(); }, []);
  useEffect(() => {
    if (!h.transaction_date) return;
    api.get(`/api/fiscal-years/natural?date=${h.transaction_date}`).then((n) => {
      setNat(n);
      if (isNew) setAllocs((as) => as.map((a) => (a.budget_id ? a : { ...a, fiscal_year_id: n.default_fiscal_year_id ? String(n.default_fiscal_year_id) : "" })));
    });
  }, [h.transaction_date]);
  const options = useBudgetOptions(allocs.map((a) => a.fiscal_year_id), type);
  const total = allocs.reduce((s, a) => s + (Number(a.amount) || 0), 0);
  const upd = (i: number, k: keyof Alloc, v: string) => setAllocs(allocs.map((a, j) => (j === i ? { ...a, [k]: v, ...(k === "fiscal_year_id" ? { budget_id: "" } : {}) } : a)));
  const openFys = fys.filter((y) => y.status !== "CLOSED");

  const changeType = (t: string) => {
    if (t === type) return;
    if (isNew) { setType(t); setAllocs(allocs.map((a) => ({ ...a, budget_id: "", invoice_number: "" }))); setH({ ...h, check_number: "" }); return; }
    setTypeDlg(t);
  };
  const confirmType = () => {
    const t = typeDlg!;
    setType(t);
    // clear/revalidate incompatible fields: budgets must be re-selected, check/invoice numbers cleared
    setAllocs(allocs.map((a) => ({ ...a, budget_id: "", invoice_number: t === "DEPOSIT" ? "" : a.invoice_number, entity_id: "" })));
    setH({ ...h, check_number: t === "DEPOSIT" ? "" : h.check_number, entity_id: txn?.entity?.is_system ? "" : h.entity_id });
    setTypeDlg(null);
  };
  const toggleSplit = () => {
    if (split) { setAllocs([{ ...allocs[0] }]); setSplit(false); }
    else {
      // BR-064: previous single amount is no longer authoritative once split
      setAllocs([{ ...allocs[0], amount: "" }, blankAlloc(allocs[0].fiscal_year_id)]);
      setSplit(true);
    }
  };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    const allocations = allocs.map((a) => ({
      ...(a.id ? { id: a.id } : {}), budget_id: Number(a.budget_id), fiscal_year_id: a.fiscal_year_id ? Number(a.fiscal_year_id) : null,
      entity_id: type === "DEPOSIT" && a.entity_id ? Number(a.entity_id) : null,
      invoice_number: type === "WITHDRAWAL" ? a.invoice_number || null : null, description: a.description || null, amount: a.amount, notes: a.notes || null,
      no_attachment: split ? a.no_attachment : false, no_attachment_reason: split && a.no_attachment ? a.no_attachment_reason || null : null,
    }));
    const header = {
      transaction_date: h.transaction_date, clear_date: h.clear_date || null, entity_id: h.entity_id ? Number(h.entity_id) : null,
      check_number: type === "WITHDRAWAL" ? h.check_number || null : null, notes: h.notes || null,
      no_attachment: h.no_attachment, no_attachment_reason: h.no_attachment ? h.no_attachment_reason || null : null,
    };
    try {
      const r = await run((confirmations) => isNew
        ? api.post("/api/transactions", { bank_account_id: account.id, transaction_type: type, ...header, allocations, confirmations, request_key: requestKey })
        : api.patch(`/api/transactions/${txn.id}`, { ...(type !== txn.transaction_type ? { transaction_type: type } : {}), ...header, allocations, confirmations }));
      if (!r) return;
      // CR-010: upload the files chosen in the form now that the transaction (and its allocations) exist
      const saved: any = r;
      const known = new Set(allocs.filter((a) => a.id).map((a) => a.id));
      const created = saved.allocations.filter((x: any) => !known.has(x.id));
      const jobs: [string, number, File][] = parentFiles.map((f) => ["transaction", saved.id, f]);
      if (split) {
        allocs.forEach((a) => {
          const id = a.id ?? created.shift()?.id;
          if (id) a.files.forEach((f) => jobs.push(["allocation", id, f]));
        });
      }
      const failed: string[] = [];
      for (const [ot, oid, f] of jobs) {
        try { await api.upload(`/api/attachments${qs({ owner_type: ot, owner_id: oid })}`, f); }
        catch (x: any) { failed.push(`${f.name}: ${x?.message || "upload failed"}`); }
      }
      if (failed.length) setUploadIssues({ id: saved.id, failed });
      else onSaved();
    } catch (x) { setErr(x); }
  };
  if (uploadIssues) {
    return (
      <Modal title={`Transaction #${uploadIssues.id} saved`} onClose={onSaved}>
        <div className="alert warn" role="alert">
          <p>The transaction was saved, but these files could not be uploaded:</p>
          <ul>{uploadIssues.failed.map((m) => <li key={m}>{m}</li>)}</ul>
          <p>Open the transaction in the register to add them again.</p>
        </div>
        <div className="actions"><button className="primary" onClick={onSaved}>Close</button></div>
      </Modal>
    );
  }
  return (
    <Modal title={isNew ? `New transaction – ${account.label}` : `Edit transaction #${txn.id}`} onClose={onClose} wide>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        {txn?.cleared ? <div className="alert warn">This transaction has cleared. Saving changes requires confirmation and is fully audited.</div> : null}
        <p className="muted">Bank account: <b>{account.label}</b> (cannot be changed after creation; wrong-account entries must be voided and re-entered).</p>
        <div className="row">
          <Field label="Type">
            <select aria-label="Transaction type" value={type} onChange={(e) => changeType(e.target.value)}>
              <option value="WITHDRAWAL">Withdrawal</option><option value="DEPOSIT">Deposit</option>
            </select>
          </Field>
          <Field label="Transaction date"><input required type="date" value={h.transaction_date} onChange={(e) => setH({ ...h, transaction_date: e.target.value })} /></Field>
          <Field label="Clear/Post date (blank = uncleared)"><input type="date" value={h.clear_date} onChange={(e) => setH({ ...h, clear_date: e.target.value })} /></Field>
          {type === "WITHDRAWAL" ? <Field label="Check #"><input value={h.check_number} onChange={(e) => setH({ ...h, check_number: e.target.value })} /></Field> : null}
        </div>
        {nat?.no_fiscal_year ? (
          <div className="alert warn" role="alert">No Fiscal Year covers {h.transaction_date}. Closest configured Fiscal Year: <b>{nat.closest?.label || "none"}</b> (shown for reference only – not assumed correct). Allocations will be flagged for Fiscal Year review.</div>
        ) : null}
        {nat?.ambiguous ? <div className="alert warn" role="alert">More than one open Fiscal Year covers this date ({nat.covering.map((c: any) => c.label).join(", ")}). Select the intended Fiscal Year explicitly for each allocation.</div> : null}
        <div className="row">
          <EntityPicker label={type === "WITHDRAWAL" ? "Payee (entity)" : split ? "Default entity (parent uses “Multiple” when entities differ)" : "Entity (payer)"}
            entities={entities} value={h.entity_id} onChange={(v) => setH({ ...h, entity_id: v })}
            extraOption={txn?.entity && !txn.entity.is_system ? { id: String(txn.entity.id), label: `${txn.entity.display_name}${txn.entity.active ? "" : " (inactive)"}` } : null} />
          <button type="button" className="small" onClick={() => setNewEnt(true)}>+ New entity</button>
        </div>
        <h3>Allocations {split ? "(split)" : ""}</h3>
        {allocs.map((a, i) => {
          const opts = options(a.fiscal_year_id, type);
          const cross = a.fiscal_year_id && nat && !nat.no_fiscal_year && !nat.covering.some((c: any) => String(c.id) === a.fiscal_year_id);
          return (
            <div key={i} className="alloc">
              <div className="row">
                <Field label="Fiscal Year">
                  <select required aria-label={`Allocation ${i + 1} Fiscal Year`} value={a.fiscal_year_id} onChange={(e) => upd(i, "fiscal_year_id", e.target.value)}>
                    <option value="">— select —</option>
                    {openFys.map((y) => <option key={y.id} value={y.id}>{y.label}</option>)}
                  </select>
                </Field>
                <Field label="Budget">
                  <select required aria-label={`Allocation ${i + 1} Budget`} value={a.budget_id} onChange={(e) => upd(i, "budget_id", e.target.value)}>
                    <option value="">— select —</option>
                    {opts.map((o: any) => <option key={o.id} value={o.id}>{o.label}{o.is_budget_zero ? " ⚠" : o.above_budget ? ` (+${money(o.above_budget)} above budget)` : ` (remaining ${money(o.remaining)})`}</option>)}
                    {a.id && a.budget_id && !opts.some((o: any) => String(o.id) === a.budget_id) ? <option value={a.budget_id}>{txn?.allocations.find((x: any) => x.id === a.id)?.budget.label} (current)</option> : null}
                  </select>
                </Field>
                <Field label="Amount"><input required aria-label={`Allocation ${i + 1} Amount`} inputMode="decimal" pattern="\d+(\.\d{1,2})?" value={a.amount} onChange={(e) => upd(i, "amount", e.target.value)} /></Field>
                {split && allocs.length > 1 ? <button type="button" className="small danger" onClick={() => setAllocs(allocs.filter((_, j) => j !== i))}>Remove</button> : null}
              </div>
              {cross ? <p className="warn-text">Budget Fiscal Year differs from the Fiscal Year covering the Transaction Date – confirmation will be required and the allocation will be flagged for review.</p> : null}
              <div className="row">
                {type === "DEPOSIT" && split ? (
                  <EntityPicker label={`Allocation ${i + 1} Entity`} entities={entities} value={a.entity_id}
                    onChange={(v) => upd(i, "entity_id", v)} placeholder="Default entity" />
                ) : null}
                {type === "WITHDRAWAL" ? <Field label="Invoice #"><input value={a.invoice_number} onChange={(e) => upd(i, "invoice_number", e.target.value)} /></Field> : null}
                <Field label="Description"><input maxLength={500} value={a.description} onChange={(e) => upd(i, "description", e.target.value)} /></Field>
                <Field label="Notes"><input value={a.notes} onChange={(e) => upd(i, "notes", e.target.value)} /></Field>
              </div>
              {split ? (
                <div className="row">
                  <label className="check">
                    <input type="checkbox" aria-label={`Allocation ${i + 1} no attachment`} checked={a.no_attachment}
                      onChange={(e) => (e.target.checked ? setNoAttDlg(i) : setAllocs(allocs.map((x, j) => (j === i ? { ...x, no_attachment: false, no_attachment_reason: "" } : x))))} />
                    No attachment will be provided for this allocation
                  </label>
                  <PendingFiles label={`Allocation ${i + 1} attachments`} files={a.files} onChange={(fl) => setAllocs(allocs.map((x, j) => (j === i ? { ...x, files: fl } : x)))} />
                  {a.no_attachment ? <Field label={`Allocation ${i + 1} reason (optional)`} hint="Without a reason, this item stays in the Fiscal Year documentation review."><input maxLength={500} value={a.no_attachment_reason} onChange={(e) => setAllocs(allocs.map((x, j) => (j === i ? { ...x, no_attachment_reason: e.target.value } : x)))} /></Field> : null}
                </div>
              ) : null}
            </div>
          );
        })}
        <div className="row">
          <button type="button" onClick={toggleSplit}>{split ? "Convert to single allocation" : "Split transaction"}</button>
          {split ? <button type="button" onClick={() => setAllocs([...allocs, blankAlloc(allocs[0].fiscal_year_id)])}>+ Add allocation</button> : null}
          <span className="total">Total (derived from allocations): <b>{money(total.toFixed(2))}</b></span>
        </div>
        <Field label="Notes"><textarea value={h.notes} onChange={(e) => setH({ ...h, notes: e.target.value })} /></Field>
        <PendingFiles label="Transaction attachments" files={parentFiles} onChange={setParentFiles} />
        <label className="check">
          <input type="checkbox" checked={h.no_attachment} onChange={(e) => (e.target.checked ? setNoAttDlg(-1) : setH({ ...h, no_attachment: false, no_attachment_reason: "" }))} />
          No attachment will be provided
        </label>
        {h.no_attachment ? (
          <Field label="Reason no attachment is available (optional)" hint="Without a reason, this item stays in the Fiscal Year documentation review."><input maxLength={500} value={h.no_attachment_reason} onChange={(e) => setH({ ...h, no_attachment_reason: e.target.value })} placeholder="e.g. Bank interest - direct deposit" /></Field>
        ) : null}
        <div className="actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" type="submit">Save</button></div>
      </GuardedForm>
      {dialog}
      {noAttDlg !== null ? (
        <Modal title="No attachment?" onClose={() => setNoAttDlg(null)}>
          <div className="alert warn" role="alert">Transactions should have supporting documentation (receipt, invoice, statement). Only mark this when no document is available — for example interest or other amounts deposited directly by the bank. The transaction will be listed as a Fiscal Year review warning.</div>
          {noAttDlg >= 0 ? <p>This applies to allocation {noAttDlg + 1} only. (If the transaction itself has an attachment or is marked, its allocations do not need one.)</p> : null}
          <div className="actions"><button onClick={() => setNoAttDlg(null)}>Cancel</button><button className="primary" onClick={() => {
            if (noAttDlg === -1) setH({ ...h, no_attachment: true });
            else setAllocs(allocs.map((x, j) => (j === noAttDlg ? { ...x, no_attachment: true } : x)));
            setNoAttDlg(null);
          }}>Mark as no attachment</button></div>
        </Modal>
      ) : null}
      {typeDlg ? (
        <Modal title="Change transaction type?" onClose={() => setTypeDlg(null)}>
          <div className="alert warn">Changing between Deposit and Withdrawal is a protected action. All budget selections will be cleared and must be re-selected with {typeDlg === "DEPOSIT" ? "Income" : "Expense"} budgets{typeDlg === "DEPOSIT" ? "; check and invoice numbers will be cleared" : ""}. The server will require a final confirmation.</div>
          <div className="actions"><button onClick={() => setTypeDlg(null)}>Cancel</button><button className="primary" onClick={confirmType}>Change to {typeDlg.toLowerCase()}</button></div>
        </Modal>
      ) : null}
      {newEnt ? <NewEntityInline onClose={() => setNewEnt(false)} onSaved={(e) => { setNewEnt(false); loadEntities().then(() => setH((x) => ({ ...x, entity_id: String(e.id) }))); }} /> : null}
    </Modal>
  );
}

function NewEntityInline({ onClose, onSaved }: { onClose: () => void; onSaved: (e: any) => void }) {
  return <EntityForm entity={{ entity_type: "ORGANIZATION" }} onClose={onClose} onSaved={onSaved} />;
}

function VoidForm({ txn, onClose, onSaved }: any) {
  const [reason, setReason] = useState("");
  const [typed, setTyped] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try { await api.post(`/api/transactions/${txn.id}/void`, { reason, confirm_irreversible: true }); onSaved(); } catch (x) { setErr(x); }
  };
  return (
    <Modal title={`Void transaction #${txn.id}`} onClose={onClose}>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        {txn.transfer ? <div className="alert warn">This is one side of a transfer. <b>Both</b> the withdrawal and the deposit will be voided.</div> : null}
        <div className="alert warn">Voiding is <b>irreversible</b>. The transaction stays visible as VOID with its allocations and attachments, but no longer affects bank balances or budget actuals.</div>
        <Field label="Void reason (required)"><textarea required value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <Field label='Type VOID to confirm'><input value={typed} onChange={(e) => setTyped(e.target.value)} /></Field>
        <div className="actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary danger" type="submit" disabled={typed !== "VOID" || !reason.trim()}>Void transaction</button></div>
      </GuardedForm>
    </Modal>
  );
}

// v1.2 CR-003: transfer between two register-enabled accounts; descriptions are generated by the server.
function TransferForm({ accounts, fromId, fys, onClose, onSaved }: any) {
  const active = accounts.filter((a: any) => a.status === "ACTIVE");
  const [f, setF] = useState({ from: String(fromId || active[0]?.id || ""), to: "", amount: "", transaction_date: todayIso(), clear_date: "", entity_id: "", notes: "", fiscal_year_id: "" });
  const [entities, setEntities] = useState<any[]>([]);
  useEffect(() => { api.get("/api/entities?status=active").then(setEntities); }, []);
  const ent = entities.find((x) => String(x.id) === f.entity_id);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const requestKey = useRef(newRequestKey()).current;
  const from = active.find((a: any) => String(a.id) === f.from);
  const to = active.find((a: any) => String(a.id) === f.to);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await api.post("/api/transfers", { from_account_id: Number(f.from), to_account_id: Number(f.to), amount: f.amount,
        transaction_date: f.transaction_date, clear_date: f.clear_date || null, notes: f.notes || null,
        entity_id: f.entity_id ? Number(f.entity_id) : null,
        fiscal_year_id: f.fiscal_year_id ? Number(f.fiscal_year_id) : null, request_key: requestKey });
      onSaved();
    } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  return (
    <Modal title="Transfer between accounts" onClose={onClose}>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        <div className="row">
          <Field label="From account">
            <select required value={f.from} onChange={(e) => setF({ ...f, from: e.target.value, to: f.to === e.target.value ? "" : f.to })}>
              {active.map((a: any) => <option key={a.id} value={a.id}>{a.label}</option>)}
            </select>
          </Field>
          <Field label="To account">
            <select required value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })}>
              <option value="">— select —</option>
              {active.filter((a: any) => String(a.id) !== f.from).map((a: any) => <option key={a.id} value={a.id}>{a.label}</option>)}
            </select>
          </Field>
        </div>
        <div className="row">
          <Field label="Amount"><input required inputMode="decimal" pattern="\d+(\.\d{1,2})?" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
          <Field label="Transaction date"><input required type="date" value={f.transaction_date} onChange={(e) => setF({ ...f, transaction_date: e.target.value })} /></Field>
          <Field label="Clear date (blank = uncleared)"><input type="date" value={f.clear_date} onChange={(e) => setF({ ...f, clear_date: e.target.value })} /></Field>
        </div>
        <Field label="Fiscal Year (only needed if ambiguous)">
          <select value={f.fiscal_year_id} onChange={(e) => setF({ ...f, fiscal_year_id: e.target.value })}>
            <option value="">Automatic</option>
            {fys.filter((y: any) => y.status !== "CLOSED").map((y: any) => <option key={y.id} value={y.id}>{y.label}</option>)}
          </select>
        </Field>
        <EntityPicker label="Entity" entities={entities} value={f.entity_id} onChange={(v) => setF({ ...f, entity_id: v })} placeholder="Type to search (optional)" />
        <Field label="Notes (optional)"><input maxLength={4000} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
        {from && to ? (
          <div className="alert info">
            A <b>withdrawal</b> will be recorded in {from.label} (“Transfer to {to.account_number_masked} for {ent ? ent.display_name : "your organization"}”) and a <b>deposit</b> in {to.label} (“Transfer from {from.account_number_masked} for {ent ? ent.display_name : "your organization"}”). Both use protected Budget 0, so budgets are not affected. Clear dates can be adjusted per account afterwards.
          </div>
        ) : null}
        <div className="actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" type="submit" disabled={busy || !f.to}>Record transfer</button></div>
      </GuardedForm>
    </Modal>
  );
}

function TransferLegForm({ txn, onClose, onSaved }: any) {
  const [clear, setClear] = useState(txn.clear_date || "");
  const [notes, setNotes] = useState(txn.notes || "");
  const [err, setErr] = useState<unknown>(null);
  const { run, dialog } = useConfirmable();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const r = await run((confirmations) => api.patch(`/api/transactions/${txn.id}`, { clear_date: clear || null, notes: notes || null, confirmations }));
      if (r) onSaved();
    } catch (x) { setErr(x); }
  };
  return (
    <Modal title={`Edit transfer leg #${txn.id}`} onClose={onClose}>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        <p className="muted">Only the clear date and notes of a transfer can be edited. To change the amount, date or accounts, void the transfer and record it again.</p>
        <Field label="Clear/Post date (blank = uncleared)"><input type="date" value={clear} onChange={(e) => setClear(e.target.value)} /></Field>
        <Field label="Notes"><textarea value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        <div className="actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" type="submit">Save</button></div>
      </GuardedForm>
      {dialog}
    </Modal>
  );
}

// v1.3 CR-011: a VOID record keeps its check number reserved; a wrongly entered number is corrected (cleared or
// changed) here, which releases it. A new number must not be used elsewhere in the account.
function VoidCheckForm({ txn, onClose, onSaved }: any) {
  const [num, setNum] = useState(txn.check_number || "");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      await api.post(`/api/transactions/${txn.id}/void-check-number`, { check_number: num.trim() || null, reason });
      onSaved();
    } catch (x) { setErr(x); }
  };
  return (
    <Modal title={`Correct check number of VOID transaction #${txn.id}`} onClose={onClose}>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        <p>A voided check keeps its number so it is never reused. Correct it only if the wrong number was entered —
          leave the box empty to release the number. The correction is noted on the record and audited.</p>
        <Field label="Check number (blank = none)"><input maxLength={20} pattern="[A-Za-z0-9-]*" value={num} onChange={(e) => setNum(e.target.value)} /></Field>
        <Field label="Reason (required)"><input required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" type="submit" disabled={(num.trim() || "") === (txn.check_number || "")}>Save check number</button></div>
      </GuardedForm>
    </Modal>
  );
}

// CR-001: only the Transaction Date of a VOID transaction may be corrected; everything else stays as recorded.
function VoidDateForm({ txn, fys, onClose, onSaved }: any) {
  const [date, setDate] = useState(txn.transaction_date);
  const [fy, setFy] = useState("");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      await api.post(`/api/transactions/${txn.id}/void-date`, { transaction_date: date, reason: reason || null,
        ...(txn.zero_dollar_void && fy ? { fiscal_year_id: Number(fy) } : {}) });
      onSaved();
    } catch (x) { setErr(x); }
  };
  return (
    <Modal title={`Correct date of VOID transaction #${txn.id}`} onClose={onClose}>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        <p>Only the Transaction Date changes. The record stays VOID with no balance or budget effect; the change is audited.
          {txn.zero_dollar_void ? " For a zero-dollar record, Budget 0 moves to the Fiscal Year covering the new date." : ""}</p>
        <Field label="Transaction date"><input type="date" required value={date} onChange={(e) => setDate(e.target.value)} /></Field>
        {txn.zero_dollar_void ? (
          <Field label="Fiscal Year (only needed if ambiguous)">
            <select value={fy} onChange={(e) => setFy(e.target.value)}>
              <option value="">Automatic</option>
              {fys.filter((y: any) => y.status !== "CLOSED").map((y: any) => <option key={y.id} value={y.id}>{y.label}</option>)}
            </select>
          </Field>
        ) : null}
        <Field label="Reason (optional)"><input maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" type="submit" disabled={date === txn.transaction_date && !fy}>Save date</button></div>
      </GuardedForm>
    </Modal>
  );
}

function ZeroVoidForm({ account, initial, fys, onClose, onSaved }: any) {
  const [f, setF] = useState({ transaction_type: "WITHDRAWAL", transaction_date: todayIso(), check_number: initial?.check_number || "", void_reason: "", fiscal_year_id: "" });
  const [err, setErr] = useState<unknown>(null);
  const requestKey = useRef(newRequestKey()).current;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.post("/api/transactions", { bank_account_id: account.id, transaction_type: f.transaction_type, transaction_date: f.transaction_date,
        check_number: f.transaction_type === "WITHDRAWAL" ? f.check_number || null : null, create_as_void: true, void_reason: f.void_reason,
        fiscal_year_id: f.fiscal_year_id ? Number(f.fiscal_year_id) : null, request_key: requestKey });
      onSaved();
    } catch (x) { setErr(x); }
  };
  return (
    <Modal title="Zero-dollar VOID accountability record" onClose={onClose}>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        <p>Documents e.g. a physically damaged unused check. Created directly as VOID for $0.00 using protected Budget 0.</p>
        <div className="row">
          <Field label="Type"><select value={f.transaction_type} onChange={(e) => setF({ ...f, transaction_type: e.target.value })}><option value="WITHDRAWAL">Withdrawal</option><option value="DEPOSIT">Deposit</option></select></Field>
          <Field label="Date"><input type="date" required value={f.transaction_date} onChange={(e) => setF({ ...f, transaction_date: e.target.value })} /></Field>
          {f.transaction_type === "WITHDRAWAL" ? <Field label="Check #"><input value={f.check_number} onChange={(e) => setF({ ...f, check_number: e.target.value })} /></Field> : null}
        </div>
        <Field label="Fiscal Year (only needed if ambiguous)">
          <select value={f.fiscal_year_id} onChange={(e) => setF({ ...f, fiscal_year_id: e.target.value })}>
            <option value="">Automatic</option>
            {fys.filter((y: any) => y.status !== "CLOSED").map((y: any) => <option key={y.id} value={y.id}>{y.label}</option>)}
          </select>
        </Field>
        <Field label="Void reason (required)"><textarea required value={f.void_reason} onChange={(e) => setF({ ...f, void_reason: e.target.value })} /></Field>
        <div className="actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" type="submit">Create VOID record</button></div>
      </GuardedForm>
    </Modal>
  );
}

function Reviews({ canResolve, canManage, account, reloadKey, onEnterCheck, onZeroCheck, onChange }: {
  canResolve: boolean; canManage: boolean; account: any; reloadKey: unknown;
  onEnterCheck: (n: number) => void; onZeroCheck: (n: number) => void; onChange: () => void;
}) {
  const [items, setItems] = useState<any[] | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const load = () => api.get("/api/fiscal-year-reviews").then(setItems, setErr);
  useEffect(() => { load(); }, []);
  const [target, setTarget] = useState<any>(null);
  const [note, setNote] = useState("");
  const confirm = async () => {
    try { await api.post(`/api/fiscal-year-reviews/${target.id}/confirm`, { note: note || null }); setTarget(null); setNote(""); load(); onChange(); } catch (x) { setErr(x); }
  };
  return (
    <section className="card">
      <h2>Pending Fiscal Year reviews</h2>
      <ErrorBox error={err} />
      {!items ? <Loading /> : items.length === 0 ? <p className="muted">No unresolved review items.</p> : (
        <table className="table compact">
          <thead><tr><th>Txn #</th><th>Date</th><th>Category</th><th>Natural FY</th><th>Budget</th><th className="num">Amount</th><th /></tr></thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id}>
                <td>{r.transaction_id}</td><td>{r.transaction_date}</td><td>{r.category === "CROSS_FY" ? "Cross-FY allocation" : "No covering Fiscal Year"}</td>
                <td>{r.natural_fiscal_year?.label || "—"}</td><td>{r.budget.label} ({r.budget.fiscal_year.display_name})</td><td className="num">{money(r.amount)}</td>
                <td>{canResolve ? <button className="small" onClick={() => setTarget(r)}>Confirm intentional</button> : null}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="hint">To reassign instead, edit the transaction and select a budget in the correct Fiscal Year.</p>
      {account ? <MissingChecks account={account} canManage={canManage} reloadKey={reloadKey} onEnter={onEnterCheck} onZero={onZeroCheck} /> : null}
      {target ? (
        <Modal title={`Confirm review for transaction #${target.transaction_id}`} onClose={() => setTarget(null)}>
          <p>Confirm that this allocation to <b>{target.budget.label}</b> ({target.budget.fiscal_year.display_name}) is intentional.</p>
          <Field label="Review note (optional)"><input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <div className="actions"><button onClick={() => setTarget(null)}>Cancel</button><button className="primary" onClick={confirm}>Mark reviewed</button></div>
        </Modal>
      ) : null}
    </section>
  );
}

// v1.3 CR-012: gaps in the check-number sequence of the selected account (warnings; they never block closing).
function MissingChecks({ account, canManage, reloadKey, onEnter, onZero }: { account: any; canManage: boolean; reloadKey: unknown; onEnter: (n: number) => void; onZero: (n: number) => void }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [ack, setAck] = useState<any>(null);
  const load = () => api.get(`/api/check-review${qs({ bank_account_id: account.id })}`).then(setD, setErr);
  useEffect(() => { load(); }, [account.id, reloadKey]);
  const nums = (m: any) => (m.count === 1 ? `${m.first_number}` : `${m.first_number}–${m.last_number} (${m.count.toLocaleString()} numbers)`);
  return (
    <div className="missing-checks">
      <h3>Possible missing checks — {account.label}</h3>
      <ErrorBox error={err} />
      {!d ? <Loading /> : d.missing.length === 0 ? <p className="muted">No gaps in the check-number sequence.</p> : (
        <table className="table compact">
          <thead><tr><th>Check #</th><th>Recorded before</th><th>Recorded after</th><th /></tr></thead>
          <tbody>
            {d.missing.map((m: any) => (
              <tr key={`${m.first_number}-${m.last_number}`}>
                <td><b>{nums(m)}</b></td>
                <td>#{m.before.check_number} · {m.before.transaction_date}</td>
                <td>#{m.after.check_number} · {m.after.transaction_date}</td>
                <td>
                  {canManage && m.count === 1 ? <button className="small" onClick={() => onEnter(m.first_number)}>Enter transaction</button> : null}
                  {canManage && m.count === 1 ? <button className="small" onClick={() => onZero(m.first_number)}>Record as VOID check</button> : null}
                  {canManage ? <button className="small" onClick={() => setAck(m)}>Confirm not missing…</button> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="hint">Checks are assumed to be used in order, from the lowest to the highest check number recorded in this account. Voided checks count as recorded.</p>
      {d?.duplicates.length ? (
        <>
          <h3>Check numbers used more than once</h3>
          <p className="hint">Recorded before duplicate check numbers were blocked. Correct the check number on the wrong record.</p>
          <ul>{d.duplicates.map((x: any) => <li key={x.check_number}>Check #{x.check_number}: {x.transactions.map((t: any) => `#${t.transaction_id} (${t.transaction_date}${t.status === "VOID" ? ", VOID" : ""})`).join(", ")}</li>)}</ul>
        </>
      ) : null}
      {ack ? <AckChecks account={account} item={ack} onClose={() => setAck(null)} onDone={() => { setAck(null); load(); }} /> : null}
    </div>
  );
}

function AckChecks({ account, item, onClose, onDone }: any) {
  const [note, setNote] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.post("/api/check-review/acknowledge", { bank_account_id: account.id, first_number: item.first_number, last_number: item.last_number, note });
      onDone();
    } catch (x) { setErr(x); }
  };
  const label = item.count === 1 ? `check #${item.first_number}` : `checks #${item.first_number}–${item.last_number}`;
  return (
    <Modal title={`Confirm ${label} not missing`} onClose={onClose}>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        <p>Use this when no transaction exists for {label} — for example the check was destroyed or lost before use, or the numbers were skipped. If the check was written, enter it instead.</p>
        <Field label="Note (required)"><input required maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. New checkbook started at 5001" /></Field>
        <div className="actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" type="submit">Confirm not missing</button></div>
      </GuardedForm>
    </Modal>
  );
}
