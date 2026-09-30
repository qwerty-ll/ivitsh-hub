import React from 'react';
import { MessageCircle, AtSign } from 'lucide-react';

const ICON = { size: 14, strokeWidth: 1.75, 'aria-hidden': true };

// Max accepts a profile link or any text (a phone, a nickname); only its own links become links
const maxHref = (value) => (/^https:\/\/max\.ru\//i.test(value) ? value : null);

/**
 * A person's contacts as they shared them: VK opens the messenger, Max shows the text (or its link).
 * Renders nothing when there are none, unless `empty` is given.
 */
const ContactLinks = ({ vk, max, name = '', empty = null }) => {
  if (!vk && !max) return empty;
  const who = name ? ` — ${name}` : '';
  return (
    <span className="contact-links">
      {vk && (
        <a className="contact-link" href={`https://vk.com/${vk}`} target="_blank" rel="noopener noreferrer"
          aria-label={`ВКонтакте ${vk}${who}`}>
          <MessageCircle {...ICON} />ВК
        </a>
      )}
      {max && (maxHref(max) ? (
        <a className="contact-link" href={maxHref(max)} target="_blank" rel="noopener noreferrer" aria-label={`Max${who}`}>
          <AtSign {...ICON} />Max
        </a>
      ) : (
        <span className="contact-link contact-link-text"><AtSign {...ICON} />Max: {max}</span>
      ))}
    </span>
  );
};

export default ContactLinks;
