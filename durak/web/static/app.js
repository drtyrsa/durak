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

// Fixed, outcome-independent display reference; see docs/luck.md.
// Smart Runner revision 3 vs Dummy, seeds 202613000–202613099, both engine seats.
// Each game contributes +|luck| and -|luck|; 200 games, 100 independent deals.
// Sorted magnitudes are rounded to 9 decimal places. Never used for match scores.
const luckReferenceV1 = Object.freeze({
  id: 'chance-v1-sr-dummy-202613000-100',
  model: 'chance-v1',
  games: 200,
  magnitudes: Object.freeze([
    0.001260713, 0.001527226, 0.001754735, 0.002128654, 0.002466936, 0.003853565, 0.004460813, 0.006479610,
    0.007101921, 0.007245484, 0.007466788, 0.012101053, 0.012167615, 0.014649330, 0.017259338, 0.018012846,
    0.019745366, 0.020806312, 0.022205949, 0.022495836, 0.023272649, 0.024939233, 0.027822689, 0.028512288,
    0.028591235, 0.031040822, 0.031631311, 0.031856554, 0.032905104, 0.035293741, 0.035696755, 0.036455957,
    0.037394335, 0.038491268, 0.040733669, 0.042143570, 0.043326360, 0.044094799, 0.045425448, 0.046800143,
    0.048432473, 0.049454419, 0.050213844, 0.050946691, 0.052243288, 0.053191182, 0.055033260, 0.055888476,
    0.057841661, 0.058911240, 0.061064568, 0.061717256, 0.061791981, 0.061970494, 0.062031068, 0.063783714,
    0.065660310, 0.065883014, 0.066571763, 0.067950937, 0.067999816, 0.069264067, 0.070305293, 0.070656851,
    0.071268691, 0.071471669, 0.071685666, 0.078877850, 0.079124818, 0.079668977, 0.080652258, 0.081539465,
    0.082948096, 0.083353360, 0.083358808, 0.084062084, 0.084454183, 0.087712889, 0.089135403, 0.091204318,
    0.091281668, 0.092051608, 0.092169485, 0.093441183, 0.093442074, 0.094307723, 0.095867847, 0.097603708,
    0.098145683, 0.098432034, 0.103110858, 0.103509091, 0.105282662, 0.106236316, 0.106518838, 0.109070939,
    0.110390766, 0.111677186, 0.111855462, 0.111900692, 0.112096678, 0.115714966, 0.116223538, 0.116356200,
    0.117643601, 0.118034230, 0.118180086, 0.118635942, 0.118824992, 0.119929820, 0.121093271, 0.122417962,
    0.132033574, 0.134065074, 0.136226981, 0.136824479, 0.137279191, 0.139797284, 0.141091557, 0.142481199,
    0.142816763, 0.142895420, 0.143163402, 0.144393252, 0.146378512, 0.147962241, 0.148365878, 0.149515176,
    0.150375140, 0.151420423, 0.154766365, 0.156575519, 0.158615111, 0.158731035, 0.159954893, 0.163948480,
    0.165750947, 0.165961237, 0.168878319, 0.169789840, 0.170838136, 0.171249296, 0.172306418, 0.173397696,
    0.175217164, 0.178722606, 0.178791315, 0.178878809, 0.190398447, 0.190541002, 0.191585808, 0.192978194,
    0.194650861, 0.195044874, 0.198460605, 0.204088103, 0.205643712, 0.208254558, 0.211297812, 0.213067180,
    0.223906302, 0.224516898, 0.234113425, 0.236248043, 0.237280228, 0.238021746, 0.240051487, 0.240174615,
    0.240385015, 0.240455088, 0.241410772, 0.242731377, 0.246465414, 0.248355830, 0.249308619, 0.255114971,
    0.255898444, 0.256831851, 0.261861439, 0.263734985, 0.273737531, 0.276538904, 0.281642420, 0.284213052,
    0.295272439, 0.295731228, 0.296288277, 0.301029463, 0.305288751, 0.306099713, 0.318127636, 0.328989860,
    0.333625190, 0.336924036, 0.337900962, 0.338221980, 0.362526931, 0.367980492, 0.375871887, 0.376626561,
  ]),
});

// Revision 3 actions replayed with chance-v2; outcomes never enter calibration.
// Seeds 202614000–202614099, both seats. The legacy reference stays unchanged.
const luckReferenceV2 = Object.freeze({
  id: 'chance-v2-sr3-dummy-202614000-100',
  model: 'chance-v2',
  games: 200,
  magnitudes: Object.freeze([
    0.000169324, 0.000349060, 0.001095464, 0.003701619, 0.005386724, 0.006891911, 0.009174498, 0.011671046,
    0.011958585, 0.012445538, 0.013452167, 0.013996441, 0.014211737, 0.015623388, 0.016305704, 0.016808228,
    0.018618479, 0.021127136, 0.021215569, 0.022209692, 0.022474700, 0.023221544, 0.024116924, 0.024298469,
    0.024919241, 0.025059300, 0.027908055, 0.028151078, 0.028818903, 0.028969584, 0.030458982, 0.031194276,
    0.032861041, 0.033186718, 0.033226417, 0.033267033, 0.035442640, 0.035580691, 0.037845865, 0.038934837,
    0.039641688, 0.040179044, 0.040345165, 0.040770569, 0.041489887, 0.041957015, 0.043178276, 0.045682162,
    0.045776033, 0.046060940, 0.046334603, 0.048670484, 0.049898390, 0.050227659, 0.050314205, 0.050634857,
    0.052943820, 0.054704860, 0.055240233, 0.055318748, 0.055512021, 0.057690223, 0.058991906, 0.059276847,
    0.062205179, 0.065737492, 0.066488381, 0.067469807, 0.067835579, 0.068136484, 0.069111355, 0.074152897,
    0.074421328, 0.078117331, 0.078215514, 0.080044360, 0.081031871, 0.081234941, 0.081958049, 0.082505084,
    0.083202479, 0.083848032, 0.084707375, 0.085238608, 0.086698529, 0.086776676, 0.087958471, 0.089445117,
    0.089777121, 0.090764737, 0.091593793, 0.093128554, 0.093151542, 0.093754029, 0.096228288, 0.096323716,
    0.099375216, 0.101902312, 0.104997952, 0.107835917, 0.108935110, 0.109102435, 0.112550149, 0.113025176,
    0.114212122, 0.117936287, 0.118351693, 0.120381675, 0.120687881, 0.123489738, 0.123651325, 0.124584412,
    0.125043747, 0.125535684, 0.125729781, 0.126247887, 0.128195981, 0.128207884, 0.129994139, 0.134993265,
    0.137007211, 0.138074925, 0.138728806, 0.141204840, 0.141401249, 0.141478171, 0.148259926, 0.149085149,
    0.153263816, 0.154507068, 0.156377946, 0.158542538, 0.160143499, 0.160362365, 0.161597461, 0.164911588,
    0.166963198, 0.167036065, 0.167649135, 0.175480058, 0.180146903, 0.184794709, 0.185556300, 0.186722288,
    0.190635725, 0.191288866, 0.191975073, 0.195000722, 0.195111138, 0.200768648, 0.202833157, 0.204452267,
    0.208969173, 0.209182594, 0.211632763, 0.212574977, 0.216340683, 0.216351744, 0.216857496, 0.219069390,
    0.219383104, 0.221694203, 0.222442582, 0.222732336, 0.224089958, 0.224592421, 0.225355311, 0.225939191,
    0.226137834, 0.226834001, 0.240635994, 0.247385704, 0.247388124, 0.248915077, 0.252185001, 0.261972374,
    0.262011412, 0.265451399, 0.273178728, 0.273180048, 0.276321206, 0.278653909, 0.287276117, 0.287539463,
    0.296871406, 0.302033637, 0.308158570, 0.309504662, 0.314667410, 0.317260155, 0.340570733, 0.344404218,
    0.345150291, 0.358143308, 0.361815826, 0.364766587, 0.386856271, 0.464125428, 0.530290165, 0.598207495,
  ]),
});
const luckReferences = Object.freeze({
  'chance-v1': luckReferenceV1,
  'chance-v2': luckReferenceV2,
});

function luckPresentation(luck) {
  if (!luck || !Number.isFinite(luck.total)) return null;
  if (!Object.prototype.hasOwnProperty.call(luckReferences, luck.model)) return null;
  const luckReference = luckReferences[luck.model];
  let below = 0;
  let equal = 0;
  for (const magnitude of luckReference.magnitudes) {
    for (const value of [-magnitude, magnitude]) {
      if (value < luck.total) below++;
      else if (value === luck.total) equal++;
    }
  }
  // Midranks handle ties; half an observation at each tail avoids claiming
  // that any finite sample identifies 0% or 100% ("perfect") luck.
  const percentile = 100 * (below + equal / 2 + 0.5) / (2 * luckReference.games + 1);
  let verdict = 'Fairly even — near the middle';
  if (percentile >= 60) {
    const label = percentile >= 90 ? 'Very lucky' : 'Lucky';
    verdict = `${label} — top ${Math.ceil(100 - percentile)}%`;
  } else if (percentile <= 40) {
    const label = percentile <= 10 ? 'Very unlucky' : 'Unlucky';
    verdict = `${label} — bottom ${Math.ceil(percentile)}%`;
  }
  return {percentile, verdict, reference: luckReference.id, games: luckReference.games};
}

function renderLuck() {
  const luck = state.game_over && state.luck;
  const presentation = luckPresentation(luck);
  for (const id of ['luck-result', 'luck-sidebar']) {
    const panel = $(id);
    panel.hidden = !presentation;
    // Preserve the expanded breakdown while reviewing the same result.
    if (!presentation || panel.dataset.revision === String(state.revision)) continue;
    panel.dataset.revision = state.revision;
    panel.replaceChildren();
    const title = document.createElement('p');
    title.className = 'eyebrow';
    title.textContent = 'Luck balance';
    const verdict = document.createElement('p');
    verdict.className = 'luck-verdict';
    verdict.textContent = presentation.verdict;
    const meter = document.createElement('meter');
    meter.min = 0;
    meter.max = 100;
    meter.value = presentation.percentile;
    meter.className = 'luck-meter';
    meter.setAttribute('aria-label', 'Your estimated luck percentile');
    meter.setAttribute('aria-valuetext', `${presentation.verdict}, compared with reference games`);
    const track = document.createElement('div');
    track.className = 'luck-track';
    track.setAttribute('aria-hidden', 'true');
    track.style.setProperty('--luck-position', `${meter.value}%`);
    const marker = document.createElement('span');
    track.append(marker);
    const labels = document.createElement('div');
    labels.className = 'luck-labels';
    for (const text of ['Unlucky', 'Typical', 'Lucky']) {
      const label = document.createElement('span');
      label.textContent = text;
      labels.append(label);
    }
    const breakdown = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Why?';
    const rows = document.createElement('dl');
    const entries = [['Starting hands', luck.opening], ['Draws', luck.refills]];
    for (const [key, name] of [['trumps', 'Trumps'], ['ranks', 'High cards'],
      ['answers', 'Cheap answers'], ['pairs', 'Pairs & sets'], ['suits', 'Suit coverage']]) {
      entries.push([name, luck.components[key]]);
    }
    if (Number.isFinite(luck.components.endgame)) {
      entries.push(['Endgame draws', luck.components.endgame]);
    }
    for (const [name, value] of entries) {
      const term = document.createElement('dt');
      term.textContent = name;
      const definition = document.createElement('dd');
      definition.textContent = Math.abs(value) < 0.005 ? 'Even' : value > 0 ? 'You' : 'Opponent';
      rows.append(term, definition);
    }
    const note = document.createElement('p');
    note.className = 'luck-note';
    note.textContent = `Compared with both players in ${presentation.games} Smart Runner–Dummy games. Starting hands and unexpected draws count; pickups and the visible trump don’t. This isn’t a win probability.`;
    if (luck.model === 'chance-v2') {
      note.textContent += ' Last draws are judged by the resulting endgame, including who attacks next.';
    }
    breakdown.append(summary, rows, note);
    panel.append(title, verdict, meter, track, labels);
    if (state.winner === 'you' && presentation.percentile <= 40) {
      const achievement = document.createElement('p');
      achievement.className = 'luck-achievement';
      achievement.textContent = 'Won against the cards';
      panel.append(achievement);
    }
    panel.append(breakdown);
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
  renderLuck();
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
