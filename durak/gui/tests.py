# -*- coding: utf-8 -*-
from collections import OrderedDict
import unittest

from mock import patch, Mock
import wx

from durak.utils.cards import DurakCard
from durak.gui.images import CardImageManager
from durak.gui.widgets import (CardButton, Card, HiddenCard, CardSizer,
                               EnemyCardSizer, TablePanel, DeckPanel,
                               ControlSizer, LabeledCardSizer)


class CardImageManagerTest(unittest.TestCase):
    def setUp(self):
        self._app = wx.PySimpleApp()

        self.cards_image_path = '1'
        self.cards_hidden_image_path = '2'
        self.card_width = 10
        self.card_height = 20
        self.manager = CardImageManager(
            self.cards_image_path,
            self.cards_hidden_image_path,
            self.card_width,
            self.card_height
        )

    def test_init(self):
        self.assertEqual(self.manager._image_path, self.cards_image_path)
        self.assertEqual(
            self.manager._hidden_image_path, self.cards_hidden_image_path
        )
        self.assertEqual(self.manager._card_width, self.card_width)
        self.assertEqual(self.manager._card_height, self.card_height)

    def test_prepare_data_prepares_card_images(self):
        all_cards = DurakCard.all()

        with patch('durak.gui.images.wx.Image') as wx_image_mock:
            self.manager._prepare_data()

            wx_image_mock.assert_any_call(
                self.cards_image_path, wx.BITMAP_TYPE_GIF
            )
            wx_image_mock.assert_any_call(
                self.cards_hidden_image_path, wx.BITMAP_TYPE_GIF
            )
            self.assertEqual(
                (wx_image_mock.return_value
                              .ConvertToBitmap
                              .return_value
                              .GetSubBitmap
                              .call_count),
                len(all_cards)
            )
            self.assertItemsEqual(
                self.manager._data.keys(),
                list(all_cards) + [self.manager.HIDDEN]
            )

    def test_get_image(self):
        self.manager._data = {}

        with patch('durak.gui.images.wx.Image') as wx_image_mock:
            result = self.manager.get_image(DurakCard('6H'))
            self.assertTrue(wx_image_mock.called)
            self.assertEqual(result, self.manager._data[DurakCard('6H')])

            wx_image_mock.reset_mock()
            result = self.manager.get_image(DurakCard('6H'))
            self.assertFalse(wx_image_mock.called)
            self.assertEqual(result, self.manager._data[DurakCard('6H')])

    def test_get_hidden_card_image(self):
        self.manager._data = {}

        with patch('durak.gui.images.wx.Image') as wx_image_mock:
            result = self.manager.get_hidden_card_image()
            self.assertTrue(wx_image_mock.called)
            self.assertEqual(result, self.manager._data[self.manager.HIDDEN])

            wx_image_mock.reset_mock()
            result = self.manager.get_hidden_card_image()
            self.assertFalse(wx_image_mock.called)
            self.assertEqual(result, self.manager._data[self.manager.HIDDEN])


class CardButtonTest(unittest.TestCase):
    def setUp(self):
        self._app = wx.PySimpleApp()

        self._image_manager_patcher = patch(
            'durak.gui.widgets.card_image_manager'
        )
        self._image_manager = self._image_manager_patcher.start()

    def tearDown(self):
        self._image_manager_patcher.stop()

    def test_card_getter(self):
        with patch('__builtin__.super'):
            button = CardButton(parent=None, card=DurakCard('6H'))
            self.assertEqual(button.card, button._card)

    def test_card_setter(self):
        with patch('__builtin__.super'):
            button = CardButton(parent=None, card=DurakCard('6H'))
            with patch.object(button, 'SetBitmapLabel') as method_mock:
                button.card = DurakCard('7S')
                self.assertEqual(button._card, DurakCard('7S'))
                method_mock.assert_called_once_with(
                    self._image_manager.get_image.return_value
                )


class CardWidgetTest(unittest.TestCase):
    """Dummy test, just checks there no exceptions on __init__"""

    def setUp(self):
        self._app = wx.PySimpleApp()

        self._image_manager_patcher = patch(
            'durak.gui.widgets.card_image_manager'
        )
        self._image_manager = self._image_manager_patcher.start()

    def tearDown(self):
        self._image_manager_patcher.stop()

    def test_init(self):
        with patch('__builtin__.super'):
            _ = Card(parent=None, card=DurakCard('6H'))


class HiddenWidgetTest(unittest.TestCase):
    """Dummy test, just checks there no exceptions on __init__"""

    def setUp(self):
        self._app = wx.PySimpleApp()

        self._image_manager_patcher = patch(
            'durak.gui.widgets.card_image_manager'
        )
        self._image_manager = self._image_manager_patcher.start()

    def tearDown(self):
        self._image_manager_patcher.stop()

    def test_init(self):
        with patch('__builtin__.super'):
            _ = HiddenCard(parent=None)


class CardSizerTest(unittest.TestCase):
    def setUp(self):
        self._app = wx.PySimpleApp()

        self.parent = object()
        self.on_click = lambda e: e
        self.sizer = CardSizer(parent=self.parent, on_click=self.on_click)

        self.trump = DurakCard('9S')

    def test_add_card_creates_button_and_inserts_it(self):
        with patch('durak.gui.widgets.CardButton') as CardButtonMock:
            with patch.object(self.sizer, '_insert_button') as insert_mock:
                with patch.object(self.sizer, 'Layout') as Layout_mock:
                    self.sizer.add_card(DurakCard('6H'))
                    CardButtonMock.assert_called_once_with(
                        parent=self.parent, card=DurakCard('6H')
                    )
                    button = CardButtonMock.return_value
                    button.Bind.assert_called_once_with(
                        wx.EVT_BUTTON, self.on_click
                    )
                    insert_mock.assert_called_once_with(button)
                    self.assertTrue(button.Show.called)
                    self.assertEqual(
                        self.sizer._buttons_dict[DurakCard('6H')], button
                    )
                    self.assertFalse(Layout_mock.called)

    def test_add_card_does_layout_if_do_layout_is_true(self):
        with patch('durak.gui.widgets.CardButton'):
            with patch.object(self.sizer, '_insert_button'):
                with patch.object(self.sizer, 'Layout') as Layout_mock:
                    self.sizer.add_card(DurakCard('6H'), do_layout=True)
                    self.assertTrue(Layout_mock.called)

    def test_insert_button(self):
        cards = [
            DurakCard('9S'), DurakCard('AH'), DurakCard('7D'), DurakCard('6H')
        ]
        children = []
        for card in cards:
            item_mock = Mock()
            item_mock.GetWindow.return_value.card = card
            children.append(item_mock)

        self.sizer._buttons_dict = dict(zip(cards, children))
        self.sizer.trump = self.trump
        new_button = Mock()
        new_button.card = DurakCard('8H')

        with patch.object(self.sizer, 'GetChildren') as GetChildren_mock:
            GetChildren_mock.return_value = children
            with patch.object(self.sizer, 'Insert') as Insert_mock:
                with patch.object(self.sizer, 'Add') as Add_mock:
                    self.sizer._insert_button(new_button)
                    Insert_mock.assert_called_once_with(2, new_button)
                    self.assertFalse(Add_mock.called)

    def test_insert_button_with_trump(self):
        cards = [
            DurakCard('JS'), DurakCard('9S'), DurakCard('AD'), DurakCard('KH')
        ]
        children = []
        for card in cards:
            item_mock = Mock()
            item_mock.GetWindow.return_value.card = card
            children.append(item_mock)

        self.sizer._buttons_dict = dict(zip(cards, children))
        self.sizer.trump = self.trump
        new_button = Mock()
        new_button.card = DurakCard('TS')

        with patch.object(self.sizer, 'GetChildren') as GetChildren_mock:
            GetChildren_mock.return_value = children
            with patch.object(self.sizer, 'Insert') as Insert_mock:
                with patch.object(self.sizer, 'Add') as Add_mock:
                    self.sizer._insert_button(new_button)
                    Insert_mock.assert_called_once_with(1, new_button)
                    self.assertFalse(Add_mock.called)

    def test_insert_button_with_lowest_card(self):
        cards = [
            DurakCard('JH'), DurakCard('9H')
        ]
        children = []
        for card in cards:
            item_mock = Mock()
            item_mock.GetWindow.return_value.card = card
            children.append(item_mock)

        self.sizer._buttons_dict = dict(zip(cards, children))
        self.sizer.trump = self.trump
        new_button = Mock()
        new_button.card = DurakCard('8H')

        with patch.object(self.sizer, 'GetChildren') as GetChildren_mock:
            GetChildren_mock.return_value = children
            with patch.object(self.sizer, 'Insert') as Insert_mock:
                with patch.object(self.sizer, 'Add') as Add_mock:
                    self.sizer._insert_button(new_button)
                    Add_mock.assert_called_once_with(new_button)
                    self.assertFalse(Insert_mock.called)

    def test_trump_getter(self):
        self.sizer._trump = DurakCard('6H')
        self.assertEqual(self.sizer.trump, self.sizer._trump)

    def test_trump_setter(self):
        self.sizer.trump = DurakCard('6H')
        self.assertEqual(self.sizer._trump, DurakCard('6H'))

    def test_remove_card_detaches_and_destroys_button(self):
        button = Mock()
        self.sizer._buttons_dict = {DurakCard('6H'): button}

        with patch.object(self.sizer, 'Detach') as Detach_mock:
            with patch.object(self.sizer, 'Layout') as Layout_mock:
                self.sizer.remove_card(DurakCard('6H'))
                Detach_mock.assert_called_once_with(button)
                self.assertTrue(button.Destroy.called)
                self.assertEqual(self.sizer._buttons_dict, {})
                self.assertFalse(Layout_mock.called)

    def test_remove_card_does_layout_if_do_layout_is_true(self):
        self.sizer._buttons_dict = {DurakCard('6H'): Mock()}

        with patch.object(self.sizer, 'Detach'):
            with patch.object(self.sizer, 'Layout') as Layout_mock:
                self.sizer.remove_card(DurakCard('6H'), do_layout=True)
                self.assertTrue(Layout_mock.called)

    def test_remove_all(self):
        self.sizer._buttons_dict = {'a': 'b', 'c': 'd'}

        with patch.object(self.sizer, 'Clear') as Clear_mock:
            with patch.object(self.sizer, 'Layout') as Layout_mock:
                self.sizer.remove_all()
                Clear_mock.assert_called_once_with(deleteWindows=True)
                self.assertEqual(self.sizer._buttons_dict, {})
                self.assertFalse(Layout_mock.called)

    def test_remove_all_does_layout_if_do_layout_is_true(self):
        with patch.object(self.sizer, 'Clear'):
            with patch.object(self.sizer, 'Layout') as Layout_mock:
                self.sizer.remove_all(do_layout=True)
                self.assertTrue(Layout_mock.called)

    def test_enable_all(self):
        self.sizer._buttons_dict = {
            DurakCard('6H'): Mock(), DurakCard('7H'): Mock()
        }

        self.sizer.enable_all()
        for button in self.sizer._buttons_dict.itervalues():
            self.assertTrue(button.Enable.called)

    def test_disable_all(self):
        self.sizer._buttons_dict = {
            DurakCard('6H'): Mock(), DurakCard('7H'): Mock()
        }

        self.sizer.disable_all()
        for button in self.sizer._buttons_dict.itervalues():
            self.assertTrue(button.Disable.called)

    def test_set_enabled_cards_enables_certain_cards(self):
        self.sizer._buttons_dict = {
            DurakCard('6H'): Mock(), DurakCard('7H'): Mock()
        }

        self.sizer.set_enabled_cards({DurakCard('7H'), })
        self.assertTrue(
            self.sizer._buttons_dict[DurakCard('6H')].Disable.called
        )
        self.assertTrue(
            self.sizer._buttons_dict[DurakCard('7H')].Enable.called
        )

    def test_cards_property(self):
        self.sizer._buttons_dict = {
            DurakCard('6H'): Mock(), DurakCard('7H'): Mock()
        }
        self.sizer._trump = DurakCard('6H')
        self.assertEqual(self.sizer.cards, set(self.sizer._buttons_dict))


class LabeledCardSizerTest(unittest.TestCase):
    def setUp(self):
        self._app = wx.PySimpleApp()

        self.parent = object()
        with patch('__builtin__.super'):
            with patch('durak.gui.widgets.wx') as wx_mock:
                self.staticbox = wx_mock.StaticBox.return_value
                self.sizer = LabeledCardSizer(parent=self.parent)

    def test_set_label(self):
        some_label = 'SOME_LABEL'
        self.sizer.set_label(some_label)

        self.staticbox.SetLabel.assert_called_once_with(some_label)


class EnemyCardSizerTest(unittest.TestCase):
    def setUp(self):
        self._app = wx.PySimpleApp()

        self.parent = object()
        self.sizer = EnemyCardSizer(parent=self.parent)

    def test_set_count_does_nothing_if_new_count_equals_old_count(self):
        cards = [Mock(), Mock()]
        self.sizer._cards = cards[:]
        self.sizer.set_count(2)
        self.assertEqual(self.sizer._cards, cards)

    def test_set_count_destroys_button_if_new_count_less_than_old_count(self):
        cards = [Mock(), Mock()]
        self.sizer._cards = cards[:]
        with patch.object(self.sizer, 'Detach') as Detach_mock:
            self.sizer.set_count(0)
            self.assertTrue(all(card.Destroy.called for card in cards))
            self.assertEqual(2, Detach_mock.call_count)
            self.assertEqual(self.sizer._cards, [])

    def test_set_count_adds_button_if_new_count_greater_than_old_count(self):
        with patch('durak.gui.widgets.HiddenCard') as HiddenCard_mock:
            with patch.object(self.sizer, 'AddMany') as AddMany_mock:
                self.sizer.set_count(2)
                HiddenCard_mock.assert_called_with(parent=self.parent)
                self.assertTrue(AddMany_mock.called)
                self.assertEqual(len(self.sizer._cards), 2)

    def test_increment(self):
        self.sizer._cards = [Mock(), Mock(), Mock()]
        with patch.object(self.sizer, 'set_count') as set_count_mock:
            self.sizer.increment(2)
            set_count_mock.assert_called_once_with(3 + 2)

    def test_decrement(self):
        self.sizer._cards = [Mock(), Mock(), Mock()]
        with patch.object(self.sizer, 'set_count') as set_count_mock:
            self.sizer.decrement(2)
            set_count_mock.assert_called_once_with(3 - 2)

    def test_count_property(self):
        cards = [Mock(), Mock()]
        self.sizer._cards = cards

        self.assertEqual(self.sizer.count, len(cards))


class TablePanelTest(unittest.TestCase):
    def setUp(self):
        self._app = wx.PySimpleApp()

        self.panel = TablePanel(parent=None)

    def test_add_card_creates_card_and_adds_it(self):
        card = DurakCard('6H')
        self.assertFalse(card in self.panel._cards)

        with patch('durak.gui.widgets.Card') as Card_mock:
            self.panel._add_card(card, (1, 2))
            Card_mock.assert_called_once_with(
                parent=self.panel, card=card, pos=(1, 2)
            )
            self.assertTrue(card in self.panel._cards)

    def test_move(self):
        card = DurakCard('6H')
        with patch.object(self.panel, '_add_card') as add_card_mock:
            self.panel.move(card)
            add_card_mock.assert_called_once_with(
                card,
                (0 + self.panel.PADDING_LEFT, self.panel.UPPER_CARD_Y_OFFSET)
            )

    def test_respond(self):
        card_mock = Mock()
        card_mock.GetPosition.return_value = wx.Point(10, 10)
        self.panel._cards[DurakCard('6H')] = card_mock
        card = DurakCard('7H')

        with patch.object(self.panel, '_add_card') as add_card_mock:
            self.panel.respond(card)
            add_card_mock.assert_called_once_with(
                card,
                wx.Point(10, 10) + wx.Point(
                    self.panel.UPPER_CARD_X_OFFSET,
                    - self.panel.UPPER_CARD_Y_OFFSET
                )
            )

    def test_give_more(self):
        card_mock = Mock()
        card_mock.GetPosition.return_value = (10, 10)
        self.panel._cards[DurakCard('6H')] = card_mock
        card = DurakCard('7H')

        self.assertEqual(self.panel._given_more, [])

        with patch.object(self.panel, '_add_card') as add_card_mock:
            self.panel.give_more(card)
            add_card_mock.assert_called_once_with(
                card,
                (
                    10 + self.panel.GIVEN_MORE_OFFSET,
                    self.panel.UPPER_CARD_Y_OFFSET
                )
            )
            self.assertEqual(self.panel._given_more, [DurakCard('7H')])

    def test_remove_all_destroys_all_the_cards(self):
        cards = [DurakCard('6H'), DurakCard('7H'), DurakCard('8H')]
        card_values = [Mock(), Mock(), Mock()]

        self.panel._cards = dict(zip(cards, card_values))
        self.panel._give_more_mode = True

        self.panel.remove_all()
        self.assertTrue(all(card.Destroy.called for card in card_values))
        self.assertEqual(self.panel._cards, {})
        self.assertEqual(self.panel._given_more, [])

    def test_cards_property(self):
        cards = [DurakCard('6H'), DurakCard('7H'), DurakCard('8H')]
        card_values = [Mock(), Mock(), Mock()]

        self.panel._cards = OrderedDict(zip(cards, card_values))

        self.assertEqual(self.panel.cards, cards)

    def test_given_more_property(self):
        cards = [DurakCard('6H'), DurakCard('7H')]
        self.panel._given_more = cards

        self.assertEqual(self.panel.given_more, cards)

    def test_is_odd_property(self):
        self.panel._cards[DurakCard('6H')] = Mock()
        self.assertTrue(self.panel._is_odd)

        self.panel._cards[DurakCard('7H')] = Mock()
        self.assertFalse(self.panel._is_odd)

    def test_pop_if_no_given_more(self):
        card_mock = Mock()
        self.panel._cards[DurakCard('6H')] = card_mock

        self.assertEqual(self.panel.pop(), DurakCard('6H'))
        self.assertDictEqual(self.panel._cards, {})
        card_mock.Destroy.assert_called()

    def test_pop_with_given_more(self):
        card_mock = Mock()
        self.panel._cards[DurakCard('6H')] = Mock()
        self.panel._cards[DurakCard('7H')] = card_mock
        self.panel._given_more = [DurakCard('7H')]

        self.assertEqual(self.panel.pop(), DurakCard('7H'))
        self.assertItemsEqual(self.panel._cards.keys(), [DurakCard('6H')])
        card_mock.Destroy.assert_called()


class DeckPanelTest(unittest.TestCase):
    def setUp(self):
        self._app = wx.PySimpleApp()

        with patch('__builtin__.super'):
            with patch.object(DeckPanel, '_create_widgets'):
                with patch.object(DeckPanel, 'SetSizeHints'):
                    self.panel = DeckPanel(parent=None)

    def test_create_widgets(self):
        with patch('durak.gui.widgets.wx') as wx_patch_mock:
            with patch('durak.gui.widgets.HiddenCard') as HiddenCardMock:
                self.panel._create_widgets()

                wx_patch_mock.StaticBitmap.assert_called_once_with(
                    parent=self.panel, pos=(0, 12)
                )
                HiddenCardMock.assert_called_once_with(
                    parent=self.panel, pos=(50, 0)
                )
                wx_patch_mock.StaticText.assert_called_once_with(
                    parent=self.panel, pos=(70, 100)
                )

                self.assertTrue(self.panel._opened_trump.Hide.called)
                self.assertTrue(self.panel._deck_top.Hide.called)


    def test_set_opened_trump_sets_trump_and_rotates_card(self):
        card = DurakCard('6H')
        self.panel._opened_trump = Mock()

        with patch('durak.gui.widgets.card_image_manager') as img_mng_mock:
            self.panel.set_opened_trump(DurakCard('6H'))
            img_mng_mock.get_image.assert_called_once_with(card)
            img = (
                img_mng_mock.get_image.return_value.ConvertToImage.return_value
            )
            img.Rotate90.assert_called_once_with(clockwise=False)
            self.panel._opened_trump.SetBitmap.assert_called_once_with(
                img.Rotate90.return_value.ConvertToBitmap.return_value
            )

        self.assertEqual(self.panel._trump_card, card)

    def test_set_card_count_sets_count(self):
        self.panel._opened_trump = Mock()
        self.panel._deck_top = Mock()
        self.panel._card_count = Mock()

        self.panel.set_card_count(10)

        self.panel._deck_top.Show.assert_called_once_with(True)
        self.panel._opened_trump.Show.assert_called_once_with(True)
        self.panel._card_count.SetLabel.assert_called_once_with('10')

    def test_set_card_count_hides_deck_if_lt_1(self):
        self.panel._opened_trump = Mock()
        self.panel._deck_top = Mock()
        self.panel._card_count = Mock()

        self.panel.set_card_count(1)

        self.panel._deck_top.Show.assert_called_once_with(False)
        self.panel._opened_trump.Show.assert_called_once_with(True)
        self.panel._card_count.SetLabel.assert_called_once_with('1')

    def test_set_card_count_hides_trump_if_0(self):
        self.panel._opened_trump = Mock()
        self.panel._deck_top = Mock()
        self.panel._card_count = Mock()
        self.panel._trump_card = DurakCard('6H')

        self.panel.set_card_count(0)

        self.panel._deck_top.Show.assert_called_once_with(False)
        self.panel._opened_trump.Show.assert_called_once_with(False)
        self.panel._card_count.SetLabel.assert_called_once_with(u'Козырь - 6H')


class ControlSizerTest(unittest.TestCase):
    def setUp(self):
        self._app = wx.PySimpleApp()
        self.parent = Mock()

        with patch('__builtin__.super'):
            with patch('durak.gui.widgets.wx') as self.wx_patch_mock:
                with patch.object(ControlSizer, 'AddMany') as self.AddManyMock:
                    self.sizer = ControlSizer(parent=self.parent)

    def test_init(self):
        buttons = [
            self.sizer._take_button,
            self.sizer._discard_button,
            self.sizer._enough_button
        ]

        for button in buttons:
            self.assertEqual(
                button, self.wx_patch_mock.Button.return_value
            )
            self.assertTrue(button.Hide.called)

        self.AddManyMock.assert_called_once_with(buttons)

    def test_set_on_take_button_click(self):
        handler = lambda e: None
        self.sizer.set_on_take_button_click(handler)
        self.sizer._take_button.Bind.assert_called_once_with(
            wx.EVT_BUTTON, handler
        )

    def test_set_on_discard_button_click(self):
        handler = lambda e: None
        self.sizer.set_on_discard_button_click(handler)
        self.sizer._discard_button.Bind.assert_called_once_with(
            wx.EVT_BUTTON, handler
        )

    def test_set_on_enough_button_click(self):
        handler = lambda e: None
        self.sizer.set_on_enough_button_click(handler)
        self.sizer._enough_button.Bind.assert_called_once_with(
            wx.EVT_BUTTON, handler
        )

    def test_hide_all(self):
        # все кнопки ссылаются на один мок, проверим счетчик на нем
        self.sizer._enough_button.Hide.reset_mock()
        self.assertEqual(self.sizer._enough_button.Hide.call_count, 0)

        self.sizer.hide_all()

        self.assertEqual(self.sizer._enough_button.Hide.call_count, 3)

    def test_show_button(self):
        buttons_map = {
            self.sizer.TAKE: self.sizer._take_button,
            self.sizer.DISCARD: self.sizer._discard_button,
            self.sizer.ENOUGH: self.sizer._enough_button,
        }

        for button_name, button in buttons_map.iteritems():
            with patch.object(ControlSizer, 'Layout') as LayoutMock:
                self.sizer.show_button(button_name)
                self.assertTrue(button.Show.called)

            self.assertTrue(LayoutMock.called)
            self.assertTrue(self.parent.Layout.called)
