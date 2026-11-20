'use strict';

// Index game boundaries first. Autoplay logs can contain many games, each with
// its own JSON body and optional diagnostics. Only parse the selected game.
function indexReplayLog(text) {
  const games = [];
  const headers = /^\uFEFF?####([^\r\n]*?)####[ \t]*\r?$/gm;
  for (const match of text.matchAll(headers)) {
    if (games.length) games[games.length - 1].end = match.index;
    games.push({title: match[1], start: match.index + match[0].length, end: text.length});
  }
  if (!games.length) throw new Error('No games found. Choose a Durak game log.');
  return games;
}

function isReplayCard(code) {
  return typeof code === 'string' && /^[6789TJQKA][CDHS]$/.test(code);
}

function replayCards(cards) {
  if (!Array.isArray(cards) || !cards.every(isReplayCard) || new Set(cards).size !== cards.length) {
    throw new Error('Invalid cards in the recorded game.');
  }
  return cards;
}

function legacyActions(move) {
  const defender = move.to_move === 'player1' ? 'player2' : 'player1';
  const actions = replayCards(move.moves_and_responds || []).map((card, i) => ({
    player: i % 2 ? defender : move.to_move, phase: i % 2 ? 'respond' : 'move', cards: [card],
  }));
  const extra = replayCards(move.given_more || []);
  if (extra.length) actions.push({player: move.to_move, phase: 'give_more', cards: extra});
  return actions;
}

function replayOutcome(game) {
  if (game.result === 's-s') return 'Draw';
  if (game.result === '1-0' || game.result === '0-1') {
    const winner = game.players[game.result === '1-0' ? 0 : 1];
    return winner === 'You' ? 'You win' : winner + ' wins';
  }
  return game.status === 'interrupted' ? 'Interrupted' : 'In progress';
}

function buildReplay(record) {
  if (!record || !isReplayCard(record.opened_trump) || !Array.isArray(record.moves) || !record.moves.length) {
    throw new Error('The game has no readable opening position.');
  }
  const players = [record.player1_name || 'Player 1', record.player2_name || 'Player 2'];
  if (!players.every(name => typeof name === 'string')) throw new Error('Invalid player names.');
  const frames = [];
  let actionNumber = 0;
  for (const [roundIndex, move] of record.moves.entries()) {
    if (!move || !['player1', 'player2'].includes(move.to_move)
        || !Number.isInteger(move.deck_count) || move.deck_count < 0 || move.deck_count > 36) {
      throw new Error('Invalid round ' + (roundIndex + 1) + '.');
    }
    let hands = [replayCards(move.player1_cards), replayCards(move.player2_cards)];
    let table = [], extra = [];
    const round = roundIndex + 1;
    const attacker = Number(move.to_move === 'player2');
    const position = {round, deck: move.deck_count, attacker};
    frames.push({...position, hands, table, extra, kind: 'round', seat: attacker});
    const actions = move.actions ?? legacyActions(move);
    if (!Array.isArray(actions)) throw new Error('Invalid actions in round ' + round + '.');
    for (const action of actions) {
      const {phase, player} = action;
      const cards = replayCards(action.cards);
      const seat = phase === 'respond' ? 1 - attacker : attacker;
      if (!['move', 'respond', 'give_more'].includes(phase) || player !== 'player' + (seat + 1)
          || (phase !== 'give_more' && cards.length > 1) || !cards.every(c => hands[seat].includes(c))) {
        throw new Error('Invalid action in round ' + round + '.');
      }
      hands = hands.slice();
      hands[seat] = hands[seat].filter(c => !cards.includes(c));
      if (phase === 'give_more') extra = extra.concat(cards);
      else table = table.concat(cards);
      frames.push({...position, hands, table, extra, kind: 'action', seat, phase, cards,
        number: ++actionNumber, analysis: action.analysis});
    }
  }
  const game = {players, trump: record.opened_trump, result: record.result, status: record.status, frames};
  // A game can end during the last refill. There is no next round snapshot
  // in this case. Use the saved stock order and the controller's refill order.
  const last = frames[frames.length - 1];
  if (['1-0', '0-1', 's-s'].includes(game.result) && last.kind === 'action'
      && (last.deck > 0 || !last.cards.length)) {
    const hands = last.hands.map(hand => hand.slice());
    const taken = last.table.length % 2 === 1;
    const defender = 1 - last.attacker;
    if (taken) hands[defender].push(...last.table, ...last.extra);
    const stock = replayCards(record.deck).slice(36 - last.deck);
    const firstDraw = taken ? defender : last.attacker;
    for (const seat of [firstDraw, 1 - firstDraw]) {
      hands[seat].push(...stock.splice(0, Math.max(0, 6 - hands[seat].length)));
    }
    if (!stock.length && hands.some(hand => !hand.length)) {
      frames.push({round: last.round, kind: 'result', hands, deck: 0, table: [], extra: []});
    }
  }
  return game;
}
