import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';

const EASE = [0.2, 0, 0, 1];

/** A dialog over the page: closes on Escape, the overlay or the cross. */
const Modal = ({ open, onClose, title, titleId, className = '', children }) => {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="modal-overlay" onClick={onClose}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2, ease: EASE }}>
          <motion.div className={`modal ${className}`} role="dialog" aria-modal="true" aria-labelledby={titleId}
            onClick={e => e.stopPropagation()}
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }} transition={{ duration: 0.24, ease: EASE }}>
            <button type="button" className="modal-close" onClick={onClose} aria-label="Закрыть окно">
              <X size={20} strokeWidth={1.75} aria-hidden="true" />
            </button>
            <h2 id={titleId}>{title}</h2>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default Modal;
