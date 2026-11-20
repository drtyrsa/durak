const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const model = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, 'static/replay-log.js'), 'utf8'), model);
const plain = value => JSON.parse(JSON.stringify(value));
const round = {player1_cards: ['6C', '6H'], player2_cards: ['7S', '9D'], to_move: 'player1', deck_count: 0};
const opening = {player1_name: 'A', player2_name: 'B', opened_trump: '7S'};

test('Unicode and CRLF logs keep independent game boundaries', () => {
  const text = '\uFEFF####Саша####\r\n{"name":"one"}\r\n####Даша####\r\n{"name":"two"}\r\n';
  const index = model.indexReplayLog(text);
  assert.deepEqual(plain(index.map(e => JSON.parse(text.slice(e.start, e.end)).name)), ['one','two']);
  assert.throws(() => model.indexReplayLog('invalid'));
});

test('backward seeks preserve both hands, pickup timing and engine attribution', () => {
  const reason = {selection: 'reserve', candidates: []};
  const actions = [
    {phase: 'move', player: 'player1', cards: ['6C']},
    {phase: 'respond', player: 'player2', cards: [], analysis: reason},
    {phase: 'give_more', player: 'player1', cards: ['6H']},
  ];
  const next = {...round, player1_cards: ['JC'], player2_cards: ['7S','9D','6C','6H']};
  const game = model.buildReplay({...opening, status: 'interrupted', moves: [{...round, actions}, next]});
  const [first, attack, take, give, newRound] = game.frames;
  assert.deepEqual(plain(first.hands), [round.player1_cards, round.player2_cards]);
  assert.deepEqual(plain(take.table), ['6C']);
  assert.deepEqual(plain(take.hands), [['6H'], ['7S','9D']]);
  assert.equal(take.analysis, reason);
  assert.equal(attack.analysis, undefined);
  assert.deepEqual(plain(give.extra), ['6H']);
  assert.deepEqual(plain(newRound.table), []);
  assert.deepEqual(plain(newRound.hands[1]), next.player2_cards);
  assert.deepEqual(plain([attack.number, take.number, give.number]), [1,2,3]);
  assert.equal(model.replayOutcome(game), 'Interrupted');
});

test('legacy bouts preserve pairs, throw-ins and round-opening snapshots', () => {
  const legacy = {...round, player1_cards: ['6C','6H','6D'], player2_cards: ['7C','9D'],
    moves_and_responds: ['6C','7C','6H'], given_more: ['6D']};
  const game = model.buildReplay({...opening, moves: [legacy]});
  assert.deepEqual(plain(game.frames.at(-1).table), ['6C','7C','6H']);
  assert.deepEqual(plain(game.frames.at(-1).extra), ['6D']);
  assert.deepEqual(plain(game.frames.at(-1).hands), [[],['9D']]);
  assert.deepEqual(plain(game.frames[2].hands), [['6H','6D'],['9D']]);
});

test('finishing during the final refill puts the stock into the correct hand', () => {
  const deck = [...'6789TJQKA'].flatMap(rank => [...'CDHS'].map(suit => rank + suit));
  const game = model.buildReplay({...opening, opened_trump: 'AS', deck, result: '0-1', moves: [{
    ...round, deck_count: 1, player1_cards: ['6C'], player2_cards: ['7C'],
    moves_and_responds: ['6C','7C'], given_more: [],
  }]});
  assert.deepEqual(plain(game.frames.at(-1).hands), [['AS'],[]]);
  assert.deepEqual(plain(game.frames.at(-1).table), []);
  assert.equal(game.frames.at(-1).deck, 0);
});

test('corrupt cards and mismatched hands fail before rendering', () => {
  for (const card of ['6D', '<b>']) {
    assert.throws(() => model.buildReplay({...opening, moves: [{...round, moves_and_responds: [card]}]}));
  }
});
