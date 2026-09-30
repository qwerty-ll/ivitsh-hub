import React from 'react';
import { Pencil, Trash2, RefreshCw, CircleAlert } from 'lucide-react';

// Building blocks shared by the tabs of the admin panel
export const ICON = { size: 16, strokeWidth: 1.75, 'aria-hidden': true };

export const Field = ({ id, label, required, hint, className = '', children }) => (
  <div className={`field ${className}`.trim()}>
    <label className="field-label" htmlFor={id}>
      {label}
      {required && <span className="admin-required" aria-hidden="true"> *</span>}
    </label>
    {children}
    {hint && <p className="field-hint" id={`${id}-hint`}>{hint}</p>}
  </div>
);

export const Toolbar = ({ id, title, description, children }) => (
  <div className="admin-toolbar">
    <div className="admin-toolbar-text">
      <h2 id={id}>{title}</h2>
      {description && <p>{description}</p>}
    </div>
    {children && <div className="admin-toolbar-actions">{children}</div>}
  </div>
);

export const RefreshButton = ({ onClick, disabled }) => (
  <button type="button" className="btn btn-secondary btn-sm" onClick={onClick} disabled={disabled}>
    <RefreshCw {...ICON} /> Обновить список
  </button>
);

export const ListSkeleton = () => (
  <div className="admin-skeleton" role="status">
    <span className="visually-hidden">Загрузка списка</span>
    {[0, 1, 2].map(i => (
      <div key={i} className="admin-skeleton-row" aria-hidden="true">
        <span className="skeleton admin-skeleton-line" />
        <span className="skeleton admin-skeleton-line admin-skeleton-line-short" />
      </div>
    ))}
  </div>
);

export const LoadError = ({ message, onRetry }) => (
  <div className="admin-error" role="alert">
    <CircleAlert {...ICON} />
    <p>Ошибка загрузки: {message}</p>
    <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
      <RefreshCw {...ICON} /> Повторить загрузку
    </button>
  </div>
);

export const RowActions = ({ label, onEdit, onDelete, deleteLabel = 'Удалить' }) => (
  <div className="admin-actions">
    {onEdit && (
      <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={onEdit}
        title="Редактировать" aria-label={`Редактировать: ${label}`}>
        <Pencil {...ICON} />
      </button>
    )}
    <button type="button" className="btn btn-ghost btn-icon btn-sm admin-icon-danger" onClick={onDelete}
      title={deleteLabel} aria-label={`${deleteLabel}: ${label}`}>
      <Trash2 {...ICON} />
    </button>
  </div>
);
