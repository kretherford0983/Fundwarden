import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import { ErrorBox, Field, Loading, Modal, GuardedForm } from "../components";
import { useMe } from "../App";

const ROLES: Record<string, [string, string][]> = {
  ADMINISTRATOR: [["ADMINISTRATOR", "Administrator"]],
  FINANCIAL: [["BUDGET_MANAGER", "Budget Manager"], ["BUDGET_USER", "Budget User"], ["REGISTER_USER", "Register User"]],
  AUDITOR: [["AUDITOR", "Auditor"]],
};

export default function Users() {
  const { me, can } = useMe();
  const [mode, setMode] = useState<string>("local");
  const [users, setUsers] = useState<any[] | null>(null);
  const [edit, setEdit] = useState<any | null>(null);
  const [reset, setReset] = useState<any | null>(null);
  const [mfaReset, setMfaReset] = useState<any | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const load = () => api.get("/api/users").then(setUsers, setErr);
  useEffect(() => {
    load();
    api.get("/api/system/status").then((s) => setMode(s.mode), () => undefined);
  }, []);
  if (!users) return <><ErrorBox error={err} /><Loading /></>;
  const manage = can("users.manage");
  return (
    <div>
      <div className="page-head">
        <h1>Users</h1>
        {manage ? <button className="primary" onClick={() => setEdit({})}>New user</button> : null}
      </div>
      <ErrorBox error={err} />
      <table className="table">
        <thead><tr><th>Username</th><th>Display name</th><th>Email</th><th>Security domain</th><th>Roles</th><th>Status</th><th>Two-step</th>{manage ? <th /> : null}</tr></thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.username}</td><td>{u.display_name}</td><td>{u.email}</td><td>{u.security_domain}</td><td>{u.roles.join(", ")}</td>
              <td>{u.active ? "Active" : "Disabled"}</td>
              <td>{u.mfa_enabled ? <span className="badge green">On</span> : <span className="badge grey">Not set up</span>}</td>
              {manage ? (
                <td className="actions-cell">
                  <button className="small" onClick={() => setEdit(u)}>Edit</button>
                  <button className="small" onClick={() => setReset(u)}>Reset password</button>
                  {u.mfa_enabled ? <button className="small" onClick={() => setMfaReset(u)}>Reset two-step</button> : null}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
      {edit ? <UserForm user={edit} ownRolesLocked={mode === "server" && edit.id === me.id} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} /> : null}
      {reset ? <ResetForm user={reset} onClose={() => setReset(null)} /> : null}
      {mfaReset ? <MfaResetForm user={mfaReset} onClose={() => { setMfaReset(null); load(); }} /> : null}
    </div>
  );
}

function UserForm({ user, ownRolesLocked = false, onClose, onSaved }: { user: any; ownRolesLocked?: boolean; onClose: () => void; onSaved: () => void }) {
  const isNew = !user.id;
  const [f, setF] = useState({
    username: user.username || "", email: user.email || "", display_name: user.display_name || "", password: "",
    security_domain: user.security_domain || "FINANCIAL", roles: (user.roles || []) as string[], active: user.active ?? true,
  });
  const [err, setErr] = useState<unknown>(null);
  const toggle = (r: string) => setF({ ...f, roles: f.roles.includes(r) ? f.roles.filter((x) => x !== r) : [...f.roles, r] });
  const setDomain = (d: string) => setF({ ...f, security_domain: d, roles: d === "FINANCIAL" ? [] : [ROLES[d][0][0]] });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      if (isNew) {
        await api.post("/api/users", { username: f.username, email: f.email, display_name: f.display_name, password: f.password,
          security_domain: f.security_domain, roles: f.roles });
      } else {
        await api.patch(`/api/users/${user.id}`, { email: f.email, display_name: f.display_name,
          security_domain: f.security_domain, roles: f.roles, active: f.active });
      }
      onSaved();
    } catch (x) {
      setErr(x);
    }
  };
  return (
    <Modal title={isNew ? "New user" : `Edit ${user.username}`} onClose={onClose}>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        {isNew ? <Field label="Username"><input required value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} /></Field> : null}
        <Field label="Email"><input required type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Display name" hint="The name shown in the top bar for this user. At least 3 characters."><input value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} /></Field>
        {isNew ? <Field label="Initial password" hint="At least 12 characters including a letter and a digit."><input required type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field> : null}
        {/* 1.7.2 (#55): in server mode an Administrator cannot change their own roles (also refused by the server) */}
        {ownRolesLocked ? <p className="hint" id="own-roles-hint">You cannot change your own security domain or roles. Another Administrator can change them for you.</p> : null}
        <fieldset disabled={ownRolesLocked} aria-describedby={ownRolesLocked ? "own-roles-hint" : undefined}>
          <legend>Security domain (exactly one)</legend>
          {Object.keys(ROLES).map((d) => (
            <label key={d} className="check"><input type="radio" name="domain" checked={f.security_domain === d} onChange={() => setDomain(d)} /> {d}</label>
          ))}
        </fieldset>
        {f.security_domain === "FINANCIAL" ? (
          <fieldset disabled={ownRolesLocked}>
            <legend>Financial roles</legend>
            {ROLES.FINANCIAL.map(([code, name]) => (
              <label key={code} className="check"><input type="checkbox" checked={f.roles.includes(code)} onChange={() => toggle(code)} /> {name}</label>
            ))}
          </fieldset>
        ) : null}
        {!isNew ? <label className="check"><input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /> Active</label> : null}
        <div className="actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" type="submit">Save</button></div>
      </GuardedForm>
    </Modal>
  );
}

function ResetForm({ user, onClose }: { user: any; onClose: () => void }) {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [done, setDone] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.post(`/api/users/${user.id}/reset-password`, { new_password: pw });
      setDone(true);
    } catch (x) {
      setErr(x);
    }
  };
  return (
    <Modal title={`Reset password for ${user.username}`} onClose={onClose}>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        {done ? <div className="alert ok">Password reset. The user's sessions were signed out.</div> : (
          <>
            <Field label="New password"><input type="password" required autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
            <div className="actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" type="submit">Reset</button></div>
          </>
        )}
      </GuardedForm>
    </Modal>
  );
}

// v1.4.1 CR-018: the user sets two-step verification up again at the next sign-in.
function MfaResetForm({ user, onClose }: { user: any; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [done, setDone] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.post(`/api/users/${user.id}/reset-mfa`, { reason });
      setDone(true);
    } catch (x) {
      setErr(x);
    }
  };
  return (
    <Modal title={`Reset two-step verification for ${user.username}`} onClose={onClose}>
      <GuardedForm onSubmit={submit}>
        <ErrorBox error={err} />
        {done ? <><div className="alert ok" role="status">Two-step verification was reset. {user.username} was signed out and will set it up again at the next sign-in.</div><div className="actions"><button type="button" className="primary" onClick={onClose}>Done</button></div></> : (
          <>
            <p>Use this when {user.username} has lost both the authenticator app and the recovery codes. Their authenticator, recovery codes and trusted browsers are removed and they are signed out everywhere.</p>
            <Field label="Reason (required)"><input required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Lost phone" /></Field>
            <div className="actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" type="submit">Reset two-step verification</button></div>
          </>
        )}
      </GuardedForm>
    </Modal>
  );
}
