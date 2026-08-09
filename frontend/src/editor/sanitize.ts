import DOMPurify from 'dompurify'

const allowedUri = /^(?:(?:(?:f|ht)tps?|mailto|tekdocs):|[^a-z]|[a-z+.-]+(?:[^a-z+.:-]|$))/i

export function sanitizeMarkdownHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'a', 'blockquote', 'br', 'code', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr',
      'input', 'li', 'mark', 'ol', 'p', 'pre', 's', 'strong', 'sup', 'table', 'tbody', 'td', 'th',
      'thead', 'tr', 'ul',
    ],
    ALLOWED_ATTR: [
      'aria-label', 'checked', 'class', 'data-callout', 'disabled', 'href', 'id', 'rel', 'title', 'type',
    ],
    ALLOWED_URI_REGEXP: allowedUri,
  })
}
