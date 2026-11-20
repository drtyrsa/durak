'use strict';

const $ = id => document.getElementById(id);
let fileText = '', entries = [], game = null, step = 0, timer = null, loadId = 0;
const shortCard = card => (card[0] === 'T' ? '10' : card[0]) + suits[card[1]].symbol;
const cardOrder = card => '6789TJQKA'.indexOf(card[0]) * 4 + 'CDHS'.indexOf(card[1]);

function moveLabel(phase, cards) {
  if (!cards.length) return {respond: 'Take', move: 'End attack', give_more: 'Finish throw-ins'}[phase];
  return {respond: 'Defend', move: 'Attack', give_more: 'Throw in'}[phase] + ' ' + cards.map(shortCard).join(' ');
}

function frameLabel(frame) {
  if (frame.kind === 'result') return replayOutcome(game);
  if (frame.kind === 'round') return game.players[frame.seat] + ' to attack';
  return game.players[frame.seat] + ' · ' + moveLabel(frame.phase, frame.cards);
}

function showDecision(frame) {
  const analysis = frame.analysis;
  $('decision').hidden = !analysis;
  if (!analysis) return;
  const label = String(analysis.strategy || '').replaceAll('_', ' ');
  let reason = analysis.reason || label;
  if (analysis.reserve_pickup?.used && isReplayCard(analysis.reserve_pickup.trump)) {
    reason = 'Saved ' + shortCard(analysis.reserve_pickup.trump);
    const covers = analysis.reserve_pickup.new_plain_covers;
    if (Array.isArray(covers) && covers.every(isReplayCard)) {
      reason += '. The pickup covers ' + covers.map(shortCard).join(' and ');
    }
    reason += '.';
  } else if (analysis.strategy === 'exact' && [-1, 0, 1].includes(analysis.outcome)) {
    reason = 'Exact endgame · ' + ['loss', 'draw', 'win'][analysis.outcome + 1] + ' with best play.';
  } else if (!analysis.reason && Number.isFinite(analysis.worlds)) {
    reason = label.replace(/^./, c => c.toUpperCase()) + ' · ' + analysis.worlds + ' trials';
    if (analysis.selection) reason += ' · ' + analysis.selection;
  }
  $('decision-summary').textContent = reason;
  const body = $('candidates').tBodies[0];
  body.replaceChildren();
  if (Array.isArray(analysis.candidates)) {
    for (const candidate of analysis.candidates) {
      if (!candidate || !Array.isArray(candidate.cards) || !candidate.cards.every(isReplayCard)
          || !Number.isFinite(candidate.score)) continue;
      const row = body.insertRow();
      const chosen = candidate.cards.length === frame.cards.length && candidate.cards.every(c => frame.cards.includes(c));
      row.classList.toggle('chosen', chosen);
      row.insertCell().textContent = moveLabel(frame.phase, candidate.cards) + (chosen ? ' ✓' : '');
      row.insertCell().textContent = candidate.score.toFixed(3);
    }
  }
  $('candidates').hidden = !body.rows.length;
  $('details-text').textContent = JSON.stringify(analysis, null, 2);
}

function setPlaying(playing) {
  clearInterval(timer);
  timer = null;
  if (playing) {
    if (step === game.frames.length - 1) seek(0);
    timer = setInterval(() => seek(step + 1), 1000);
  }
  $('play').textContent = playing ? 'Pause' : 'Play';
}

function seek(index) {
  const end = game.frames.length - 1;
  const timeline = $('timeline');
  timeline.children[step]?.removeAttribute('aria-current');
  step = Math.max(0, Math.min(index, end));
  const frame = game.frames[step];
  const current = timeline.children[step];
  current.setAttribute('aria-current', 'step');
  const bounds = timeline.getBoundingClientRect();
  const target = current.getBoundingClientRect();
  if (target.bottom > bounds.bottom) timeline.scrollTop += target.bottom - bounds.bottom;
  if (target.top < bounds.top) timeline.scrollTop -= bounds.top - target.top;

  frame.hands.forEach((hand, seat) => {
    const panel = $('hand-' + (seat + 1));
    const sorted = hand.slice().sort((a, b) => cardOrder(a) - cardOrder(b));
    panel.replaceChildren(...sorted.map(card => makeCard(card, game.trump)));
    panel.setAttribute('aria-label', game.players[seat] + ' hand');
    $('name-' + (seat + 1)).textContent = game.players[seat];
    $('count-' + (seat + 1)).textContent = hand.length + (hand.length === 1 ? ' card' : ' cards');
  });
  drawTable($('table-cards'), frame.table, frame.extra, game.trump);
  for (const card of $('table-cards').querySelectorAll('[data-card]')) {
    if (frame.cards?.includes(card.dataset.card)) card.classList.add('just-played');
  }
  drawDeck($('deck-cards'), $('deck-label'), frame.deck, game.trump);
  $('round-number').textContent = 'Round ' + frame.round;
  $('step-label').textContent = frameLabel(frame);
  $('scrub').value = step;
  $('scrub').setAttribute('aria-valuetext', 'Round ' + frame.round + ', ' + frameLabel(frame));
  $('step-count').textContent = (step + 1) + ' / ' + (end + 1);
  $('first').disabled = $('prev').disabled = step === 0;
  $('next').disabled = $('last').disabled = step === end;
  $('play').disabled = $('scrub').disabled = end === 0;
  if (step === end) setPlaying(false);
  showDecision(frame);
}

function manualSeek(index) {
  setPlaying(false);
  seek(index);
}

function selectGame(index) {
  setPlaying(false);
  $('file-error').hidden = true;
  try {
    const entry = entries[index];
    const record = JSON.parse(fileText.slice(entry.start, entry.end));
    game = buildReplay(record);
  } catch (error) {
    game = null;
    $('timeline').replaceChildren();
    $('replay-content').hidden = entries.length < 2;
    document.querySelector('.replay-room').hidden = true;
    $('moves-section').hidden = true;
    $('decision').hidden = true;
    showError('Could not read game ' + (index + 1) + '. ' + error.message);
    return;
  }
  $('replay-content').hidden = false;
  document.querySelector('.replay-room').hidden = false;
  $('moves-section').hidden = false;
  $('game-outcome').textContent = replayOutcome(game);
  $('scrub').max = game.frames.length - 1;
  const items = game.frames.map((frame, i) => {
    const button = document.createElement('button');
    button.className = 'timeline-step ' + frame.kind;
    button.dataset.step = i;
    if (frame.kind === 'round') {
      button.textContent = 'Round ' + frame.round + ' · ' + frameLabel(frame);
    } else {
      const number = document.createElement('span');
      number.textContent = frame.number ?? '';
      button.append(number, frameLabel(frame));
    }
    return button;
  });
  $('timeline').replaceChildren(...items);
  $('details').open = false;
  seek(0);
}

function showError(message) {
  $('file-error').textContent = message;
  $('file-error').hidden = false;
}

async function openLog(name, read) {
  const id = ++loadId;
  setPlaying(false);
  try {
    const text = await read();
    if (id !== loadId) return;
    const index = indexReplayLog(text);
    fileText = text;
    entries = index;
    $('file-name').textContent = name;
    $('open-panel').hidden = true;
    $('change-file').hidden = false;
    $('game-picker').hidden = index.length < 2;
    $('game-select').replaceChildren(...index.map((entry, i) => new Option((i + 1) + '. ' + entry.title, i)));
    selectGame(0);
  } catch (error) {
    if (id === loadId) showError(error.message);
  }
}

function openFile(file) {
  if (file) openLog(file.name, () => file.text());
}

$('open-file').onclick = $('change-file').onclick = () => $('log-file').click();
$('log-file').onchange = event => {
  openFile(event.target.files[0]);
  event.target.value = '';
};
$('game-select').onchange = event => selectGame(Number(event.target.value));
$('first').onclick = () => manualSeek(0);
$('prev').onclick = () => manualSeek(step - 1);
$('next').onclick = () => manualSeek(step + 1);
$('last').onclick = () => manualSeek(game.frames.length - 1);
$('scrub').oninput = event => manualSeek(Number(event.target.value));
$('play').onclick = () => setPlaying(!timer);
$('timeline').onclick = event => {
  const button = event.target.closest('[data-step]');
  if (button) manualSeek(Number(button.dataset.step));
};
document.addEventListener('keydown', event => {
  if (!game || event.altKey || event.ctrlKey || event.metaKey ||
      event.target.closest('input, select, textarea, summary, pre')) return;
  const keys = {ArrowLeft: step - 1, ArrowRight: step + 1, Home: 0, End: game.frames.length - 1};
  if (Object.hasOwn(keys, event.key)) {
    event.preventDefault();
    manualSeek(keys[event.key]);
  } else if (event.code === 'Space' && !event.target.closest('button, a') && !$('play').disabled) {
    event.preventDefault();
    setPlaying(!timer);
  }
});
document.addEventListener('visibilitychange', () => { if (document.hidden) setPlaying(false); });
const app = document.querySelector('.replay-app');
for (const name of ['dragover', 'drop']) {
  document.addEventListener(name, event => {
    if (!event.dataTransfer.types.includes('Files')) return;
    event.preventDefault();
    app.classList.toggle('dragging', name === 'dragover');
    if (name === 'drop') openFile(event.dataTransfer.files[0]);
  });
}
document.addEventListener('dragleave', event => { if (!event.relatedTarget) app.classList.remove('dragging'); });

const savedFile = new URLSearchParams(location.search).get('game');
if (savedFile) openLog(savedFile, async () => {
  const response = await fetch('/api/replay/' + encodeURIComponent(savedFile));
  if (!response.ok) throw new Error('Open the saved log to replay this game.');
  return response.text();
});
