'use strict';

const $ = (id) => document.getElementById(id);
const suits = {C: {symbol: '♣', name: 'Clubs', singular: 'clubs'}, D: {symbol: '♦', name: 'Diamonds', singular: 'diamonds'}, H: {symbol: '♥', name: 'Hearts', singular: 'hearts'}, S: {symbol: '♠', name: 'Spades', singular: 'spades'}};
const ranks = {T: '10', J: 'Jack', Q: 'Queen', K: 'King', A: 'Ace'};
const pipPositions = {
  6: [[1,1],[1,3],[3,1],[3,3],[5,1],[5,3]],
  7: [[1,1],[1,3],[2,2],[3,1],[3,3],[5,1],[5,3]],
  8: [[1,1],[1,3],[2,2],[3,1],[3,3],[4,2],[5,1],[5,3]],
  9: [[1,1],[1,3],[2,1],[2,3],[3,2],[4,1],[4,3],[5,1],[5,3]],
  T: [[1,1],[1,3],[2,1],[2,2],[2,3],[4,1],[4,2],[4,3],[5,1],[5,3]],
};
let state = null;
let busy = false;
let automaticTimer = null;
let toastTimer = null;
let selected = new Set();
let previousTable = new Set();
let resultShown = null;
let connected = true;

function cardName(code) {
  return `${ranks[code[0]] || code[0]} of ${suits[code[1]].singular}`;
}

function makeCard(code, interactive = false) {
  if (!/^[6789TJQKA][CDHS]$/.test(code)) throw new Error('Invalid card received.');
  const rank = code[0];
  const suit = suits[code[1]].symbol;
  const label = rank === 'T' ? '10' : rank;
  const card = document.createElement(interactive ? 'button' : 'div');
  card.className = 'playing-card' + ('DH'.includes(code[1]) ? ' red' : '');
  card.dataset.card = code;
  card.setAttribute('aria-label', cardName(code));
  if (!interactive) card.setAttribute('role', 'img');
  const corner = `<span class="rank">${label}</span><span class="suit">${suit}</span>`;
  let face;
  if (pipPositions[rank]) {
    face = '<span class="pips">' + pipPositions[rank].map(([row,col]) => `<span class="pip ${row > 3 ? 'reverse' : ''}" style="grid-row:${row};grid-column:${col}">${suit}</span>`).join('') + '</span>';
  } else if (rank === 'A') {
    face = `<span class="large-suit">${suit}</span>`;
  } else {
    face = `<span class="court"><span class="court-letter">${rank}</span><span class="court-suit">${suit}</span></span>`;
  }
  card.innerHTML = `<span class="corner">${corner}</span>${face}<span class="corner bottom">${corner}</span>`;
  if (state?.trump?.[1] === code[1]) {
    card.insertAdjacentHTML('beforeend', '<span class="trump-diamond" aria-hidden="true">◆</span>');
    card.setAttribute('aria-label', cardName(code) + ', trump');
  }
  return card;
}

function cardBack() {
  const card = document.createElement('div');
  card.className = 'card-back';
  card.setAttribute('aria-hidden', 'true');
  card.innerHTML = '<span class="back-emblem"><span>♠</span></span>';
  return card;
}

function toast(message) {
  $('toast').textContent = message;
  $('toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 5000);
}

async function request(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Durak-Token': state.token},
    body: JSON.stringify({...body, revision: state.revision}),
  });
  const data = await response.json();
  if (!response.ok) {
    if (data.state) state = data.state;
    throw new Error(data.error || 'That action could not be completed.');
  }
  return data;
}

async function mutate(path, body = {}) {
  if (busy) return false;
  clearTimeout(automaticTimer);
  busy = true;
  render();
  let success = false;
  try {
    state = await request(path, body);
    connected = true;
    selected.clear();
    success = true;
  } catch (error) {
    toast(error.message || 'Cannot reach the table. Keep durak-web running and refresh.');
    // Never replay a move after a lost response; read the authoritative state.
    try {
      state = await request('/api/state');
      connected = true;
    } catch (_) {
      connected = false;
    }
  } finally {
    busy = false;
    render();
    scheduleAutomatic();
  }
  return success;
}

function scheduleAutomatic() {
  clearTimeout(automaticTimer);
  if (!state?.started || !connected || busy || state.game_over || state.error || state.human_turn || document.querySelector('dialog[open]')) return;
  automaticTimer = setTimeout(() => mutate('/api/step'), state.phase === 'dealing' ? 850 : 550);
}

function renderHand() {
  const focusCard = document.activeElement?.dataset.card;
  const hand = $('your-hand');
  hand.replaceChildren();
  const legal = new Set(state.legal_cards);
  for (const code of [...selected]) if (!legal.has(code)) selected.delete(code);
  state.hand.forEach((code, index) => {
    const card = makeCard(code, true);
    const offset = index - (state.hand.length - 1) / 2;
    card.style.setProperty('--angle', (state.hand.length <= 10 ? offset * 1.35 : 0) + 'deg');
    card.style.setProperty('--lift', (state.hand.length <= 10 ? Math.abs(offset) * .9 : 0) + 'px');
    const canSelect = legal.has(code) && state.human_turn && !state.error && !state.game_over;
    card.disabled = busy || !connected || !canSelect || (state.phase === 'giving_more' && selected.size >= state.max_throw && !selected.has(code));
    card.classList.toggle('playable', canSelect);
    card.classList.toggle('selected', selected.has(code));
    if (state.phase === 'giving_more') card.setAttribute('aria-pressed', selected.has(code) ? 'true' : 'false');
    card.addEventListener('click', () => {
      if (state.phase === 'giving_more') {
        if (selected.has(code)) selected.delete(code); else selected.add(code);
        render();
      } else {
        mutate('/api/action', {action: 'play', cards: [code]});
      }
    });
    hand.append(card);
  });
  if (focusCard) hand.querySelector(`[data-card="${focusCard}"]`)?.focus({preventScroll: true});
  $('hand-count').textContent = state.hand.length;
  $('hand-guide').textContent = state.phase === 'giving_more' && state.human_turn
    ? `${selected.size} selected · Click again to undo`
    : state.game_over ? '' : 'Click a highlighted card to play';
}

function renderTable() {
  const table = $('table-cards');
  table.replaceChildren();
  const addCard = (pair, code, classes = '') => {
    const card = makeCard(code);
    if (classes) card.classList.add(...classes.split(' '));
    if (!previousTable.has(code)) card.classList.add('card-enter');
    pair.append(card);
  };
  for (let i = 0; i < state.on_table.length; i += 2) {
    const pair = document.createElement('div');
    pair.className = 'table-pair';
    addCard(pair, state.on_table[i], state.on_table[i+1] ? '' : 'uncovered');
    if (state.on_table[i+1]) addCard(pair, state.on_table[i+1], 'defence');
    table.append(pair);
  }
  for (const code of state.given_more) {
    const pair = document.createElement('div');
    pair.className = 'table-pair';
    addCard(pair, code, 'throw-in');
    table.append(pair);
  }
  previousTable = new Set([...state.on_table, ...state.given_more]);
  table.hidden = previousTable.size === 0;

  const opponentHand = $('opponent-hand');
  opponentHand.replaceChildren();
  const visible = Math.min(state.opponent_count, 10);
  for (let i = 0; i < visible; i++) {
    const back = cardBack();
    const offset = i - (visible - 1) / 2;
    back.style.setProperty('--angle', offset * 4 + 'deg');
    back.style.setProperty('--lift', Math.abs(offset) * 2 + 'px');
    opponentHand.append(back);
  }
  $('opponent-count').textContent = `${state.opponent_count} card${state.opponent_count === 1 ? '' : 's'} in hand`;
  opponentHand.setAttribute('aria-label', `Opponent has ${state.opponent_count} hidden cards`);

  const deck = $('deck-cards');
  deck.replaceChildren();
  if (state.deck_count > 0) {
    deck.append(makeCard(state.trump));
    const backs = Math.min(state.deck_count - 1, 4);
    for (let layer = backs - 1; layer >= 0; layer--) {
      const back = cardBack();
      back.style.setProperty('--stack-offset', `${layer * 2}px`);
      deck.append(back);
    }
  } else {
    const empty = document.createElement('div');
    empty.className = 'empty-deck';
    empty.textContent = suits[state.trump[1]].symbol;
    deck.append(empty);
  }
  $('deck-label').textContent = state.deck_count ? `${state.deck_count} in the deck` : 'Deck is empty';
}

function renderTurn() {
  const engineName = state.engines.find((engine) => engine.id === state.engine).name;
  let title, hint;
  if (!connected) {
    title = 'Disconnected';
    hint = 'Keep durak-web running, then reconnect.';
  } else if (state.error) {
    title = 'Engine error';
    hint = state.error;
  } else if (state.game_over) {
    title = {you: 'You win', opponent: `${engineName} wins`, draw: 'Draw'}[state.winner];
    hint = '';
  } else if (state.phase === 'dealing') {
    title = state.taking ? 'Collecting cards…' : 'Clearing table…';
    hint = '';
  } else if (!state.human_turn) {
    title = `${engineName} is thinking…`;
    hint = '';
  } else if (state.phase === 'moving') {
    title = 'Your attack';
    hint = state.on_table.length ? 'Match a rank or end the attack.' : 'Choose a card.';
  } else if (state.phase === 'responding') {
    title = 'Your defence';
    hint = state.legal_cards.length ? 'Beat the attack or take the cards.' : 'No valid defence. Take the cards.';
  } else {
    title = `${engineName} takes`;
    hint = state.max_throw && state.legal_cards.length ? `Choose up to ${state.max_throw} throw-in${state.max_throw === 1 ? '' : 's'}, then Done.` : 'No cards to add. Finish the attack.';
  }
  $('turn-title').textContent = title;
  $('turn-hint').textContent = hint;
  $('turn-dot').classList.toggle('waiting', !state.human_turn);
  $('thinking-dots').classList.toggle('visible', !state.human_turn && !state.game_over && !state.error);
  const actions = $('turn-actions');
  actions.replaceChildren();
  for (const action of state.actions) {
    const button = document.createElement('button');
    button.className = 'button primary';
    button.disabled = busy || !connected;
    button.textContent = {take: 'Take cards', finish: 'End attack', throw: selected.size ? `Done · ${selected.size}` : 'Done'}[action];
    button.addEventListener('click', () => mutate('/api/action', {action, cards: action === 'throw' ? [...selected] : []}));
    actions.append(button);
  }
  if (state.game_over || state.error) {
    const button = document.createElement('button');
    button.className = 'button primary';
    button.textContent = 'New game';
    button.disabled = busy || !connected;
    button.addEventListener('click', () => startNewGame());
    actions.append(button);
  }
  if (!connected) {
    const button = document.createElement('button');
    button.className = 'button primary';
    button.textContent = 'Reconnect';
    button.addEventListener('click', async () => {
      try {
        state = await request('/api/state');
        connected = true;
        render();
        scheduleAutomatic();
      } catch (_) { toast('Cannot reach the table yet. Is durak-web still running?'); }
    });
    actions.append(button);
  }
}

function render() {
  if (!state) return;
  document.querySelectorAll('.new-trigger, #play-again').forEach((button) => {
    button.disabled = busy || !connected;
  });
  const select = $('engine-select');
  const choices = JSON.stringify(state.engines.map(({id, name}) => [id, name]));
  if (select.dataset.choices !== choices) {
    select.replaceChildren();
    for (const engine of state.engines) {
      const option = document.createElement('option');
      option.value = engine.id;
      option.textContent = engine.name;
      select.append(option);
    }
    select.dataset.choices = choices;
  }
  select.value = state.engine;
  select.disabled = busy || !connected;
  if (!state.started) return;
  if (state.phase !== 'giving_more') selected.clear();
  const engine = state.engines.find((item) => item.id === state.engine);
  for (const id of ['opponent-name', 'score-name']) $(id).textContent = engine.name;
  $('opponent-avatar').textContent = engine.name[0].toUpperCase();
  $('game-label').textContent = 'Game ' + state.game_number;
  const trump = suits[state.trump[1]];
  $('trump-name').textContent = trump.name;
  $('trump-symbol').textContent = trump.symbol;
  $('trump-symbol').classList.toggle('red', 'DH'.includes(state.trump[1]));
  $('deck-count').textContent = state.deck_count;
  $('discard-count').textContent = state.discarded_count;
  for (const who of ['you', 'opponent', 'draw']) $('score-' + who).textContent = state.scores[who];
  const games = Object.values(state.scores).reduce((a,b) => a+b, 0);
  $('games-count').textContent = `${games} game${games === 1 ? '' : 's'}`;
  $('activity').replaceChildren();
  for (const event of state.history.slice(-3).reverse()) {
    const li = document.createElement('li');
    // Also update activity received from a server that is already running.
    li.textContent = event.text.replace(/^New deal\./, 'New game.');
    if (event.cards.length) {
      const cards = document.createElement('span');
      cards.className = 'activity-cards';
      cards.textContent = event.cards.map((c) => (c[0] === 'T' ? '10' : c[0]) + suits[c[1]].symbol).join(' ');
      li.append(cards);
    }
    $('activity').append(li);
  }
  renderHand();
  renderTable();
  renderTurn();
  if (state.game_over && resultShown !== state.revision) {
    resultShown = state.revision;
    $('result-title').textContent = {you: 'You win', opponent: `${engine.name} wins`, draw: 'Draw'}[state.winner];
    if (!document.querySelector('dialog[open]')) $('result-dialog').showModal();
  }
}

async function startNewGame(engineId) {
  if (!state || busy || !connected) return;
  clearTimeout(automaticTimer);
  document.querySelectorAll('dialog[open]').forEach((dialog) => dialog.close());
  await mutate('/api/new', engineId === undefined ? {} : {engine: engineId});
}

document.querySelectorAll('.new-trigger').forEach((button) => button.addEventListener('click', () => startNewGame()));
$('play-again').addEventListener('click', () => startNewGame());
document.querySelectorAll('.rules-trigger').forEach((button) => button.addEventListener('click', () => {
  clearTimeout(automaticTimer);
  $('rules-dialog').showModal();
}));
document.querySelectorAll('.dialog-close, .dialog-dismiss').forEach((button) => button.addEventListener('click', () => button.closest('dialog').close()));
document.querySelectorAll('dialog').forEach((dialog) => dialog.addEventListener('close', scheduleAutomatic));
$('engine-select').addEventListener('change', () => {
  const engineId = $('engine-select').value;
  if (engineId !== state?.engine) startNewGame(engineId);
});

(async () => {
  try {
    state = await request('/api/state');
    if (!state.started) state = await request('/api/new', {});
    render();
    scheduleAutomatic();
  } catch (error) {
    $('turn-title').textContent = 'Disconnected';
    $('turn-hint').textContent = 'Keep durak-web running, then refresh this page.';
    toast(error.message);
  }
})();
