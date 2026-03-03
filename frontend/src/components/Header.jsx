import React, { useState, useEffect, useRef } from 'react';
import { FiUsers, FiChevronDown, FiChevronRight, FiCheck } from 'react-icons/fi';
import '../styles/Header.css';

export default function Header({ patientName, studyDate, modality, selectedStudy, onStudyChange }) {
  const [patients, setPatients]       = useState([]);
  const [open, setOpen]               = useState(false);
  const [loading, setLoading]         = useState(false);
  const [expandedPid, setExpandedPid] = useState(null);
  const dropdownRef                   = useRef(null);

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Auto-expand the patient that owns the currently selected study
  useEffect(() => {
    if (!patients.length || !selectedStudy) return;
    const owner = patients.find((p) => p.studies.some((s) => s.study_id === selectedStudy));
    if (owner) setExpandedPid(owner.patient_id);
  }, [patients, selectedStudy]);

  const fetchPatients = async () => {
    if (patients.length) { setOpen((o) => !o); return; }
    setLoading(true);
    try {
      const res  = await fetch('/api/patients');
      const data = await res.json();
      setPatients(data.patients ?? []);
      setOpen(true);
    } catch (e) {
      console.error('Failed to fetch patients', e);
    } finally {
      setLoading(false);
    }
  };

  const selectStudy = (study_id) => {
    onStudyChange?.(study_id);
    setOpen(false);
  };

  const togglePatient = (pid) =>
    setExpandedPid((prev) => (prev === pid ? null : pid));

  const now = new Date().toLocaleDateString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
  });

  return (
    <header className="header">
      <div className="header-brand">
        <img src="/logo.png" alt="RadioGaga logo" className="header-logo-img" />
        <span className="header-logo-text">Radio<strong>Gaga</strong></span>
        <span className="header-divider" />
        <span className="header-subtitle">Medical Imaging Dashboard</span>
      </div>

      <div className="header-patient">
        <div className="header-info-chip">
          <span className="chip-label">Patient</span>
          <span className="chip-value">{patientName}</span>
        </div>
        <div className="header-info-chip">
          <span className="chip-label">Study Date</span>
          <span className="chip-value">{studyDate}</span>
        </div>
        <div className="header-info-chip">
          <span className="chip-label">Modality</span>
          <span className={`chip-value modality-badge ${modality !== '—' ? 'modality-active' : ''}`}>
            {modality}
          </span>
        </div>
      </div>

      {/* Patient → Study two-level picker */}
      <div className="header-patient-picker" ref={dropdownRef}>
        <button
          className={`picker-btn${open ? ' picker-btn--open' : ''}`}
          onClick={fetchPatients}
          disabled={loading}
        >
          <FiUsers size={13} />
          <span>{loading ? 'Loading…' : 'List patients'}</span>
          <FiChevronDown size={12} className={`picker-chevron${open ? ' picker-chevron--open' : ''}`} />
        </button>

        {open && patients.length > 0 && (
          <div className="picker-dropdown">
            {patients.map((p) => {
              const isExpanded   = expandedPid === p.patient_id;
              const ownsSelected = p.studies.some((s) => s.study_id === selectedStudy);
              return (
                <div key={p.patient_id} className="picker-patient">
                  {/* ── Patient row ── */}
                  <button
                    className={`picker-patient-row${ownsSelected ? ' picker-patient-row--active' : ''}`}
                    onClick={() => togglePatient(p.patient_id)}
                  >
                    <span className="picker-patient-chevron">
                      {isExpanded ? <FiChevronDown size={11} /> : <FiChevronRight size={11} />}
                    </span>
                    <span className="picker-patient-id">{p.patient_id}</span>
                    {p.patient_name && (
                      <span className="picker-patient-name">{p.patient_name}</span>
                    )}
                    <span className="picker-patient-meta">
                      {[p.patient_sex, p.patient_age != null ? `${p.patient_age}y` : null]
                        .filter(Boolean).join(' · ')}
                    </span>
                    <span className="picker-patient-count">
                      {p.studies.length} stud{p.studies.length !== 1 ? 'ies' : 'y'}
                    </span>
                  </button>

                  {/* ── Studies sub-list ── */}
                  {isExpanded && (
                    <div className="picker-studies">
                      {p.studies.map((s) => (
                        <button
                          key={s.study_id}
                          className={`picker-study-row${s.study_id === selectedStudy ? ' picker-study-row--active' : ''}`}
                          onClick={() => selectStudy(s.study_id)}
                        >
                          <span className="picker-study-label">
                            {s.study_date_fmt || s.study_name?.split(' ')[0] || '—'}
                          </span>
                          <span className="picker-study-id">
                            {s.study_name?.split(' ').slice(1).join(' ') || s.study_name}
                          </span>
                          {s.study_id === selectedStudy && (
                            <FiCheck size={11} className="picker-check" />
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="header-right">
        <span className="header-date">{now}</span>
        <span className="header-status">
          <span className="status-dot" />
          Live
        </span>
      </div>
    </header>
  );
}
