// Attribution is a suggestion, never an account binding or a balance grant.
// Entity owns sign-in, explicit acceptance, signed requests and all receipts.
(function () {
  'use strict';
  var storageKey = 'dew-pending-referral-v1';
  var query = new URLSearchParams(location.search);
  var match = /^\/invite\/([^/]+)\/?$/.exec(location.pathname);
  var supplied = match || ['ref', 'code', 'referral'].some(function (key) { return query.has(key); });
  var pending = {};
  try { pending = JSON.parse(sessionStorage.getItem(storageKey) || '{}') || {}; } catch (_) {}
  if (typeof pending !== 'object' || Array.isArray(pending)) pending = {};
  if (supplied) {
    var code = match ? match[1] : query.get('ref') || query.get('code') || query.get('referral') || '';
    try { code = decodeURIComponent(code); } catch (_) { code = ''; }
    pending = { code: code.trim(), app: query.get('app') || '', platform: query.get('platform') || query.get('source_platform') || 'web' };
  }
  // Source hints persist with the code; losing a hint must never turn a store
  // invitation into a web purchase flow after a reload or sign-in.
  if (!supplied && (query.has('platform') || query.has('source_platform')))
    pending.platform = query.get('platform') || query.get('source_platform');
  if (!supplied && query.has('app')) pending.app = query.get('app');
  var code = typeof pending.code === 'string' ? pending.code : '';
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(code)) code = '';
  var platform = String(pending.platform || 'web').toLowerCase();
  var direct = ['web', 'direct', 'desktop', 'fdroid', 'f-droid', 'linux', 'windows', 'macos'].indexOf(platform) !== -1;
  pending = { code: code, app: typeof pending.app === 'string' ? pending.app.slice(0, 128) : '', platform: platform };
  try { sessionStorage.setItem(storageKey, JSON.stringify(pending)); } catch (_) {}
  var language = (query.get('lang') || navigator.language || 'en').slice(0, 2).toLowerCase();
  var translations = {
    en: { title: 'Your Dew invitation', code: 'Invitation code', gift: 'Sign in, then accept your invitation to receive 20 Dew immediately. No purchase or minimum is required.', terms: 'You can have one inviter across Waozi apps. Your public name, alias or account ID and acceptance date appear in their referrals list. They earn 5% Dew on your paid Dew purchases, with no invitation limit or end date.', manual: 'Keep this code. If a download or sign-in loses the link, enter it in My referrals after signing in.', open: 'Sign in / accept invitation', dashboard: 'My referrals', restricted: 'Accept your invitation here to receive the welcome gift. To buy Dew, return to the app that sent this invitation and use its own payment options. This page will not open web top-up for that edition.', unknown: 'The invitation link has no valid code. You can enter a code manually in My referrals.', forget: 'Dismiss this link', return: 'Return to Dew' },
    de: { title: 'Deine Dew-Einladung', code: 'Einladungscode', gift: 'Melde dich an und nimm die Einladung an, um sofort 20 Dew zu erhalten. Kein Kauf und kein Mindestbetrag nötig.', terms: 'Du kannst in allen Waozi-Apps zusammen einen Einladenden haben. Dein öffentlicher Name, Alias oder deine Konto-ID und das Annahmedatum erscheinen in dessen Empfehlungsliste. Die Person erhält dauerhaft 5 % Dew auf deine bezahlten Dew-Käufe. Einladungen sind unbegrenzt.', manual: 'Bewahre diesen Code auf. Geht der Link beim Herunterladen oder Anmelden verloren, gib ihn nach der Anmeldung unter Meine Empfehlungen ein.', open: 'Anmelden / Einladung annehmen', dashboard: 'Meine Empfehlungen', restricted: 'Nimm deine Einladung hier an, um das Willkommensgeschenk zu erhalten. Kehre für Dew-Käufe zu der App zurück, die diese Einladung gesendet hat, und nutze deren Zahlungsmöglichkeiten. Diese Seite öffnet für diese Ausgabe keine Web-Aufladung.', unknown: 'Der Einladungslink enthält keinen gültigen Code. Du kannst unter Meine Empfehlungen einen Code von Hand eingeben.', forget: 'Diesen Link schließen', return: 'Zurück zu Dew' },
    es: { title: 'Tu invitación de Dew', code: 'Código de invitación', gift: 'Inicia sesión y acepta la invitación para recibir 20 Dew de inmediato. No se requiere compra ni importe mínimo.', terms: 'Solo puedes tener una persona que te invite entre todas las apps de Waozi. Tu nombre público, alias o ID de cuenta y la fecha de aceptación aparecen en su lista de referidos. Recibe un 5 % de Dew por tus compras pagadas de Dew, sin límite de invitaciones ni fecha de finalización.', manual: 'Guarda este código. Si una descarga o el inicio de sesión pierde el enlace, introdúcelo en Mis referidos después de iniciar sesión.', open: 'Iniciar sesión / aceptar invitación', dashboard: 'Mis referidos', restricted: 'Acepta tu invitación aquí para recibir el regalo de bienvenida. Para comprar Dew, vuelve a la app que envió la invitación y usa sus opciones de pago. Esta página no abrirá la recarga web para esa edición.', unknown: 'El enlace no contiene un código válido. Puedes introducir uno manualmente en Mis referidos.', forget: 'Descartar este enlace', return: 'Volver a Dew' }
  };
  if (!translations[language]) language = 'en';
  var words = translations[language];
  var requested = !!supplied || /^\/(invite|referrals)\/?$/.test(location.pathname) || query.get('view') === 'referrals' || !!code || !direct;
  var panel = document.getElementById('referral-landing');
  function text(id, value) { document.getElementById(id).textContent = value; }
  text('referral-title', words.title);
  text('referral-code-label', words.code);
  text('referral-code', code);
  text('referral-gift', words.gift + (direct ? '' : ' ' + words.restricted));
  text('referral-terms', words.terms);
  text('referral-manual', code ? words.manual : words.unknown);
  text('referral-open', code ? words.open : words.dashboard);
  text('referral-forget', words.forget);
  panel.lang = language;
  panel.hidden = !requested;
  document.getElementById('referral-code-label').hidden = !code;
  document.getElementById('referral-forget').onclick = function () {
    try { sessionStorage.removeItem(storageKey); } catch (_) {}
    location.href = '/?lang=' + language + (direct ? '' : '&platform=' + encodeURIComponent(platform));
  };
  window.DewReferral = {
    code: code, requested: requested, fundingAllowed: direct,
    // No opaque install attribution or private account material is retained.
    sourceApp: pending.app,
    ready: function () { panel.hidden = true; },
    open: function () {
      if (!window.Module) return;
      Module.referralCode = code;
      Module.referralRequested = true;
    }
  };
  document.getElementById('referral-open').onclick = window.DewReferral.open;
})();
