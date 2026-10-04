const phone = document.querySelector('.phone');
const brandRow = document.querySelector('.header-brand-row');
const pageRow = document.querySelector('.header-page-row');
const title = document.querySelector('.page-name');
const actions = document.querySelector('.header-actions');
const menuTrigger = document.querySelector('.menu-trigger');
const drawerContainer = document.querySelector('.drawer-container');
const drawer = document.querySelector('.drawer');
const appSurface = document.querySelector('.app-surface');
const homeContent = document.querySelector('.home-content');
const otherContent = document.querySelector('.other-content');
const toast = document.querySelector('.toast');
let toastTimer;

function updateBrandIcons() {
  const source = phone.dataset.theme === 'light' ? 'assets/concurse-light.png' : 'assets/concurse-dark.png';
  phone.querySelectorAll('[data-brand-icon]').forEach(icon => { icon.src = source; });
  document.querySelector('link[rel="icon"]').href = source;
}

function setVariant(variant, updateUrl = true) {
  const expanded = variant === 'expanded';
  phone.dataset.variant = expanded ? 'expanded' : 'compact';
  if (expanded) {
    pageRow.append(title, actions);
    pageRow.removeAttribute('aria-hidden');
  } else {
    brandRow.append(title, actions);
    pageRow.setAttribute('aria-hidden', 'true');
  }
  document.querySelectorAll('[data-variant].variant-button').forEach(button => {
    const selected = button.dataset.variant === phone.dataset.variant;
    button.classList.toggle('is-selected', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  document.querySelector('#preview-name').textContent = expanded ? 'B · Topo em duas linhas' : 'A · Topo compacto';
  document.querySelector('#variant-explanation').textContent = expanded
    ? 'Marca e menu na primeira linha. Título e ações na segunda, com mais espaço para nomes longos.'
    : 'Menu à esquerda, ícone e título no centro, duas ações à direita. Botões de 48 px, sem encostar na barra do sistema.';
  document.querySelector('#preview-caption').textContent = expanded
    ? 'O topo ocupa 120 px após a barra do Android. Mais espaço para o título, mantendo as cinco abas na base.'
    : 'O topo ocupa 64 px após a barra do Android. Cinco destinos na base, sempre na mesma linha.';
  if (updateUrl) history.replaceState(null, '', expanded ? '?opcao=b' : '?opcao=a');
}

function closeDrawer() {
  drawerContainer.hidden = true;
  appSurface.inert = false;
  menuTrigger.setAttribute('aria-expanded', 'false');
  menuTrigger.focus({ preventScroll: true });
}

function openDrawer() {
  drawerContainer.hidden = false;
  appSurface.inert = true;
  menuTrigger.setAttribute('aria-expanded', 'true');
  document.querySelector('.drawer-close').focus({ preventScroll: true });
}

function showFeedback(message) {
  if (!drawerContainer.hidden) closeDrawer();
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 4000);
}

const titles = { 'Início': 'Início', 'Biblioteca': 'Biblioteca', 'Buscar': 'Buscar provas', 'Progresso': 'Progresso', 'Perfil': 'Perfil & Configurações' };
function navigateTo(name, secondary = false) {
  if (!drawerContainer.hidden) closeDrawer();
  title.textContent = titles[name] || name;
  homeContent.hidden = name !== 'Início';
  otherContent.hidden = name === 'Início';
  document.querySelector('#destination-title').textContent = titles[name] || name;
  document.querySelector('#destination-description').textContent = secondary
    ? 'Uma ferramenta secundária, acessada pelo menu lateral.'
    : 'O título e a barra inferior acompanham a tela escolhida.';
  document.querySelectorAll('.bottom-link').forEach(button => {
    const selected = button.dataset.go === name || (secondary && ['Ranking', 'Caderno de erros'].includes(name) && button.dataset.go === 'Progresso');
    button.classList.toggle('is-active', selected);
    if (selected) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  const content = document.querySelector('.app-content');
  content.scrollTop = 0;
}

document.querySelectorAll('.variant-button').forEach(button => button.addEventListener('click', () => setVariant(button.dataset.variant)));
document.querySelector('#device-width').addEventListener('change', event => { phone.style.setProperty('--device-width', `${event.target.value}px`); });
document.querySelector('#theme-toggle').addEventListener('click', event => {
  const light = phone.dataset.theme === 'dark';
  phone.dataset.theme = light ? 'light' : 'dark';
  updateBrandIcons();
  event.currentTarget.setAttribute('aria-pressed', String(light));
  event.currentTarget.querySelector('span').textContent = light ? 'Ver tema escuro' : 'Ver tema claro';
});
menuTrigger.addEventListener('click', openDrawer);
document.querySelector('.drawer-close').addEventListener('click', closeDrawer);
document.querySelector('.drawer-scrim').addEventListener('click', closeDrawer);
document.querySelectorAll('[data-feedback]').forEach(button => button.addEventListener('click', () => showFeedback(button.dataset.feedback)));
document.querySelectorAll('[data-go]').forEach(button => button.addEventListener('click', () => navigateTo(button.dataset.go)));
document.querySelectorAll('[data-secondary]').forEach(button => button.addEventListener('click', () => navigateTo(button.dataset.secondary, true)));
document.addEventListener('keydown', event => {
  if (drawerContainer.hidden) return;
  if (event.key === 'Escape') { event.preventDefault(); closeDrawer(); }
  if (event.key === 'Tab') {
    const focusable = [...drawer.querySelectorAll('button, [tabindex="0"]')];
    const first = focusable[0]; const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
});
setVariant(new URLSearchParams(location.search).get('opcao') === 'b' ? 'expanded' : 'compact', false);
updateBrandIcons();
