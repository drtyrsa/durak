'use strict';

const suits = {C: {symbol: '♣', name: 'Clubs', singular: 'clubs'}, D: {symbol: '♦', name: 'Diamonds', singular: 'diamonds'}, H: {symbol: '♥', name: 'Hearts', singular: 'hearts'}, S: {symbol: '♠', name: 'Spades', singular: 'spades'}};
const ranks = {T: '10', J: 'Jack', Q: 'Queen', K: 'King', A: 'Ace'};
const pipPositions = {
  6: [[1,1],[1,3],[3,1],[3,3],[5,1],[5,3]],
  7: [[1,1],[1,3],[2,2],[3,1],[3,3],[5,1],[5,3]],
  8: [[1,1],[1,3],[2,2],[3,1],[3,3],[4,2],[5,1],[5,3]],
  9: [[1,1],[1,3],[2,1],[2,3],[3,2],[4,1],[4,3],[5,1],[5,3]],
  T: [[1,1],[1,3],[2,1],[2,2],[2,3],[4,1],[4,2],[4,3],[5,1],[5,3]],
};

function cardName(code) {
  return `${ranks[code[0]] || code[0]} of ${suits[code[1]].singular}`;
}

function makeCard(code, trump, interactive = false) {
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
  if (trump[1] === code[1]) {
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

function drawTable(table, onTable, givenMore, trump, previousTable) {
  table.replaceChildren();
  const addCard = (pair, code, classes = '') => {
    const card = makeCard(code, trump);
    if (classes) card.classList.add(...classes.split(' '));
    if (previousTable && !previousTable.has(code)) card.classList.add('card-enter');
    pair.append(card);
  };
  for (let i = 0; i < onTable.length; i += 2) {
    const pair = document.createElement('div');
    pair.className = 'table-pair';
    addCard(pair, onTable[i], onTable[i+1] ? '' : 'uncovered');
    if (onTable[i+1]) addCard(pair, onTable[i+1], 'defence');
    table.append(pair);
  }
  for (const code of givenMore) {
    const pair = document.createElement('div');
    pair.className = 'table-pair';
    addCard(pair, code, 'throw-in');
    table.append(pair);
  }
  table.hidden = !onTable.length && !givenMore.length;
}

function drawDeck(deck, label, count, trump) {
  deck.replaceChildren();
  if (count > 0) {
    deck.append(makeCard(trump, trump));
    const backs = Math.min(count - 1, 4);
    for (let layer = backs - 1; layer >= 0; layer--) {
      const back = cardBack();
      back.style.setProperty('--stack-offset', `${layer * 2}px`);
      deck.append(back);
    }
  } else {
    const empty = document.createElement('div');
    empty.className = 'empty-deck';
    empty.textContent = suits[trump[1]].symbol;
    deck.append(empty);
  }
  label.textContent = count ? `${count} in the deck` : 'Deck is empty';
}
