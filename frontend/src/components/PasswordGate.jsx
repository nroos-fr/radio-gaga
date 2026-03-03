import React, { useState, useEffect } from 'react';

const SESSION_KEY = 'rg_auth';
const PASSWORD = import.meta.env.VITE_APP_PASSWORD;

export default function PasswordGate({ children }) {
  const [unlocked, setUnlocked] = useState(() => sessionStorage.getItem(SESSION_KEY) === '1');
  const [input, setInput] = useState('');
  const [error, setError] = useState(false);

  // If no password is configured, pass through immediately
  if (!PASSWORD) return children;
  if (unlocked) return children;

  function handleSubmit(e) {
    e.preventDefault();
    if (input === PASSWORD) {
      sessionStorage.setItem(SESSION_KEY, '1');
      setUnlocked(true);
    } else {
      setError(true);
      setInput('');
    }
  }

  return (
    <div style={styles.overlay}>
      <form onSubmit={handleSubmit} style={styles.card}>
        <div style={styles.title}>radio-gaga</div>
        <div style={styles.subtitle}>Enter password to continue</div>
        <input
          type="password"
          value={input}
          onChange={e => { setInput(e.target.value); setError(false); }}
          placeholder="Password"
          autoFocus
          style={{ ...styles.input, ...(error ? styles.inputError : {}) }}
        />
        {error && <div style={styles.errorMsg}>Incorrect password</div>}
        <button type="submit" style={styles.button}>Unlock</button>
      </form>
    </div>
  );
}

const styles = {
  overlay: {
    position: 'fixed',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--header-bg)',
  },
  card: {
    background: 'var(--surface)',
    borderRadius: 'var(--radius-lg)',
    padding: '36px 40px',
    display: 'flex',
    flexDirection: 'column',
    gap: '14px',
    width: '320px',
    boxShadow: 'var(--shadow-md)',
  },
  title: {
    fontSize: '18px',
    fontWeight: 700,
    color: 'var(--text)',
    textAlign: 'center',
    letterSpacing: '.02em',
  },
  subtitle: {
    fontSize: '13px',
    color: 'var(--text-2)',
    textAlign: 'center',
    marginBottom: '4px',
  },
  input: {
    padding: '9px 12px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-dark)',
    fontSize: '13px',
    fontFamily: 'var(--font)',
    outline: 'none',
    width: '100%',
    background: 'var(--surface-alt)',
    color: 'var(--text)',
  },
  inputError: {
    borderColor: '#ef4444',
  },
  errorMsg: {
    fontSize: '12px',
    color: '#ef4444',
    marginTop: '-6px',
  },
  button: {
    padding: '9px',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--accent)',
    color: '#fff',
    fontWeight: 600,
    fontSize: '13px',
    cursor: 'pointer',
    fontFamily: 'var(--font)',
    marginTop: '4px',
  },
};
