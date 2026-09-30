import React, { useRef, useState } from 'react';
import { Paperclip, Link2, FileText, Trash2, Loader2, ExternalLink } from 'lucide-react';
import { useToast } from '../context/ToastContext';
import { attachmentsApi } from '../services/api';
import { formatSize } from '../utils/tasks';

const ICON = { strokeWidth: 1.75, 'aria-hidden': true };
const ACCEPT = '.pdf,.png,.jpg,.jpeg,.webp,.docx,.xlsx,.pptx,.zip';

/**
 * Files and links of a task or an announcement.
 * owner: 'tasks' | 'associations/posts' | 'events' | 'achievements'; canAdd shows the upload controls
 * (and adding links unless links={false});
 * onChange reloads the owner after an addition or removal.
 */
const Attachments = ({ owner, ownerId, items, canAdd, onChange, links = true, hint = '' }) => {
  const toast = useToast();
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [link, setLink] = useState({ url: '', title: '' });

  const upload = async (e) => {
    const files = [...(e.target.files || [])];
    e.target.value = '';
    if (!files.length) return;
    setUploading(true);
    for (const file of files) {
      try {
        await attachmentsApi.upload(owner, ownerId, file);
      } catch (err) {
        toast.show(`${file.name}: ${err.message || 'не загрузился'}`, 'error', 5000);
      }
    }
    setUploading(false);
    onChange();
  };

  const addLink = async (e) => {
    e.preventDefault();
    try {
      await attachmentsApi.addLink(owner, ownerId, link.url.trim(), link.title.trim());
      setLink({ url: '', title: '' });
      setLinkOpen(false);
      onChange();
    } catch (err) {
      toast.show(err.message || 'Не удалось добавить ссылку', 'error');
    }
  };

  const remove = async (a) => {
    if (!window.confirm(`Удалить «${a.title}»?`)) return;
    try {
      await attachmentsApi.remove(a.id);
      onChange();
    } catch (err) {
      toast.show(err.message || 'Не удалось удалить', 'error');
    }
  };

  return (
    <div className="attach">
      {items.length > 0 && (
        <ul className="attach-list">
          {items.map(a => (
            <li key={a.id} className="attach-item">
              {a.kind === 'file' ? (
                <a className="attach-link" href={attachmentsApi.href(a.id)} download>
                  <FileText size={18} {...ICON} />
                  <span className="attach-name">{a.title}</span>
                  <span className="attach-meta tabular">{formatSize(a.size)}</span>
                </a>
              ) : (
                <a className="attach-link" href={a.url} target="_blank" rel="noopener noreferrer nofollow">
                  <ExternalLink size={18} {...ICON} />
                  <span className="attach-name">{a.title}</span>
                </a>
              )}
              {a.uploaded_by && <span className="attach-meta attach-who">{a.uploaded_by.split(' ').slice(0, 2).join(' ')}</span>}
              {a.can_delete && (
                <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => remove(a)} aria-label={`Удалить ${a.title}`} title="Удалить">
                  <Trash2 size={16} {...ICON} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {items.length === 0 && !canAdd && <p className="attach-empty">Файлов и ссылок нет.</p>}

      {canAdd && (
        <>
          <div className="attach-actions">
            <input ref={fileRef} type="file" accept={ACCEPT} multiple className="visually-hidden" onChange={upload}
              id={`attach-file-${owner.replace('/', '-')}-${ownerId}`} />
            <button type="button" className="btn btn-secondary btn-sm" disabled={uploading} onClick={() => fileRef.current?.click()}>
              {uploading ? <Loader2 size={16} className="spin-icon" {...ICON} /> : <Paperclip size={16} {...ICON} />}
              {uploading ? 'Загружаем…' : 'Прикрепить файл'}
            </button>
            {links && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setLinkOpen(v => !v)} aria-expanded={linkOpen}>
                <Link2 size={16} {...ICON} />Добавить ссылку
              </button>
            )}
          </div>
          <p className="attach-hint">{hint || 'PDF, изображения, Word, Excel, PowerPoint или ZIP, до 10 МБ.'}</p>
          {linkOpen && (
            <form className="attach-link-form" onSubmit={addLink}>
              <input className="input" type="url" required placeholder="https://…" value={link.url} aria-label="Адрес ссылки"
                onChange={e => setLink({ ...link, url: e.target.value })} autoFocus />
              <input className="input" placeholder="Название (необязательно)" value={link.title} maxLength={200} aria-label="Название ссылки"
                onChange={e => setLink({ ...link, title: e.target.value })} />
              <button type="submit" className="btn btn-primary btn-sm">Добавить</button>
            </form>
          )}
        </>
      )}
    </div>
  );
};

export default Attachments;
