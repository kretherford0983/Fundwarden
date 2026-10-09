import { useEffect, useState, type FormEvent } from "react";
import { api, preAuthCsrf } from "../api";
import { ErrorBox, Field, GuardedForm, LegalLinks } from "../components";
import { ForgotPassword } from "./Recovery";

export default function Login({ workspace, onLogin, legal }: { workspace: string; onLogin: () => void; legal?: { license?: string; source_url?: string } }) {
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [forgot, setForgot] = useState(false); // 1.8.0 (#113)
  useEffect(() => {
    preAuthCsrf();
  }, []);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      await preAuthCsrf();
      await api.post("/api/auth/login", { username, password });
      setP("");
      onLogin();
    } catch (x) {
      setErr(x);
    }
  };
  if (forgot) return <div className="center"><ForgotPassword onBack={() => setForgot(false)} /></div>;
  return (
    <div className="center">
      <GuardedForm className="card auth-card" onSubmit={submit}>
        <h1>Sign in</h1>
        <p className="muted">{workspace}</p>
        <ErrorBox error={err} />
        <Field label="Username"><input required autoComplete="username" value={username} onChange={(e) => setU(e.target.value)} /></Field>
        <Field label="Password"><input required type="password" autoComplete="current-password" value={password} onChange={(e) => setP(e.target.value)} /></Field>
        <button className="primary" type="submit">Sign in</button>
        <button type="button" className="linklike forgot-link" onClick={() => { setErr(null); setForgot(true); }}>Forgot password?</button>
      </GuardedForm>
      {legal?.license ? <p className="hint login-legal"><img className="logo" src="/favicon.svg" alt="" width={16} height={16} /> PennyWarden · <LegalLinks license={legal.license} sourceUrl={legal.source_url} /></p> : null}
    </div>
  );
}
