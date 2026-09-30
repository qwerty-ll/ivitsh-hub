import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ChevronDown, HelpCircle, Search, MessageCircle, MessageSquarePlus } from 'lucide-react';
import { motion } from 'framer-motion';
import DOMPurify from 'dompurify';
import { contentApi } from '../services/api';
import { openChat } from '../utils/chat';
import SectionIcon from '../components/SectionIcon';

const ICON = { strokeWidth: 1.75 };

const FAQItem = ({ id, question, answer, isOpen, onClick }) => {
  const buttonId = `faq-q-${id}`;
  const panelId = `faq-a-${id}`;
  return (
    <li className={`faq-item ${isOpen ? 'is-open' : ''}`}>
      <h2 className="faq-question">
        <button
          type="button"
          id={buttonId}
          className="faq-trigger"
          onClick={onClick}
          aria-expanded={isOpen}
          aria-controls={panelId}
        >
          <span>{question}</span>
          <ChevronDown size={20} {...ICON} className="faq-chevron" aria-hidden="true" />
        </button>
      </h2>
      {isOpen && (
        <motion.div
          id={panelId}
          role="region"
          aria-labelledby={buttonId}
          className="faq-answer"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="faq-answer-body" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(answer || '') }} />
        </motion.div>
      )}
    </li>
  );
};

const FaqPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [openIndex, setOpenIndex] = useState(null);

  const [faqItems, setFaqItems] = useState([]);
  const [loading, setLoading] = useState(true);
  // /faq?q=… (links from the assistant) opens the list already filtered
  const [query, setQuery] = useState(() => searchParams.get('q') || '');

  // Search questions and answer text (answers are HTML, so tags are ignored)
  const visibleItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    const indexed = faqItems.map((item, idx) => ({ item, idx }));
    if (!q) return indexed;
    return indexed.filter(({ item }) => {
      const answerText = (item.answer || '').replace(/<[^>]*>/g, ' ');
      return `${item.question} ${answerText}`.toLowerCase().includes(q);
    });
  }, [faqItems, query]);

  useEffect(() => {
    contentApi.getFaq()
      .then(res => setFaqItems(Array.isArray(res) ? res : []))
      .catch(err => console.warn('FAQ load failed:', err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="container cm-page faq-page">
      <header className="page-header">
        <div className="page-heading">
          <SectionIcon section="faq" size="lg" />
          <div>
            <h1>Частые вопросы</h1>
            <p className="page-subtitle">Короткие ответы на то, что студенты спрашивают чаще всего.</p>
          </div>
        </div>
      </header>

      <div className="faq-layout">
        <div className="faq-main">
          {faqItems.length > 3 || query ? (
            <div className="cm-search faq-search">
              <label htmlFor="faq-search" className="visually-hidden">Поиск по вопросам</label>
              <Search size={18} {...ICON} className="cm-search-icon" aria-hidden="true" />
              <input
                id="faq-search"
                type="search"
                className="input"
                placeholder="Например, стипендия или студенческий"
                value={query}
                onChange={(e) => { setQuery(e.target.value); setOpenIndex(null); }}
              />
            </div>
          ) : null}

          {loading ? (
            <ul className="faq-list" aria-busy="true" aria-label="Загрузка вопросов">
              {[0, 1, 2].map(i => (
                <li key={i} className="faq-item faq-item-skeleton" aria-hidden="true">
                  <span className="skeleton faq-skel" />
                </li>
              ))}
            </ul>
          ) : visibleItems.length > 0 ? (
            <ul className="faq-list">
              {visibleItems.map(({ item, idx }) => (
                <FAQItem
                  key={item.id || idx}
                  id={item.id || idx}
                  question={item.question}
                  answer={item.answer}
                  isOpen={openIndex === idx}
                  onClick={() => setOpenIndex(openIndex === idx ? null : idx)}
                />
              ))}
            </ul>
          ) : query ? (
            <div className="empty-state" role="status">
              <Search size={32} {...ICON} aria-hidden="true" />
              <h2 className="cm-empty-title">Ничего не нашлось по запросу «{query.trim()}»</h2>
              <p>Попробуйте другое слово или спросите ВИТШика — он знает больше, чем написано здесь.</p>
            </div>
          ) : (
            <div className="empty-state">
              <HelpCircle size={32} {...ICON} aria-hidden="true" />
              <h2 className="cm-empty-title">Список частых вопросов пока пуст</h2>
              <p>Администратор добавляет вопросы через панель управления. А пока спросите на форуме — там отвечают студенты и кураторы.</p>
            </div>
          )}
        </div>

        {/* NOT FOUND AN ANSWER */}
        <aside className="faq-help" aria-labelledby="faq-help-heading">
          <img src="/img/mascot-160.png" alt="" className="faq-help-mascot" width="72" height="72" />
          <h2 id="faq-help-heading">Не нашли ответ?</h2>
          <p>ВИТШик ответит сразу, а на форуме помогут сокурсники и кураторы.</p>
          <div className="faq-help-actions">
            <button type="button" className="btn btn-primary" onClick={openChat}>
              <MessageCircle size={16} {...ICON} aria-hidden="true" />
              Спросить ВИТШика
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => navigate('/forum')}>
              <MessageSquarePlus size={16} {...ICON} aria-hidden="true" />
              Спросить на форуме
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
};

export default FaqPage;
