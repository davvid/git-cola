try:
    import gitlab
except ImportError:
    gitlab = None
from qtpy import QtGui
from qtpy import QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtCore import Signal

from . import defs
from . import standard
from . import text
from .. import cmds
from .. import gitcmds
from .. import icons
from .. import qtutils
from .. import utils
from ..i18n import N_
from ..qtutils import get


ENABLED = gitlab is not None


def editor(context, run=True):
    """Return a ForgeEditor instance"""
    view = ForgeEditor(context, parent=qtutils.active_window())
    if run:
        view.show()
        view.exec_()
    return view


def lineedit(context, hint):
    """Create a HintedLineEdit with a preset minimum width"""
    widget = text.HintedLineEdit(context, hint)
    width = qtutils.text_width(widget.font(), 'M')
    widget.setMinimumWidth(width * 32)
    return widget


class ForgeEditor(standard.Dialog):
    """Enable API access to software forges"""

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.setWindowTitle(N_('Edit Forges'))
        if parent is not None:
            self.setWindowModality(Qt.WindowModal)

        self.context = context
        self.current_name = ''
        self.current_url = ''
        self.current_token = ''
        self.current_backend = ''
        self.forge_list = []
        self.forges = standard.ListWidget()
        tooltip = N_(
            'Add and remove forges using the Add(+) and Delete(-) buttons.\n'
            'Forges URLs can be changed using the editor or by selecting one from the\n'
            'the list and pressing "Enter", or by double-clicking an iten im the list.'
        )
        self.forges.setToolTip(tooltip)
        self.editor = ForgeEditorWidget(context, self)
        self.save_button = qtutils.create_button(
            text=N_('Save'), icon=icons.save(), default=True
        )
        self.reset_button = qtutils.create_button(
            text=N_('Reset'), icon=icons.discard()
        )

        icon = icons.add()
        tooltip = N_('Add new forge')
        self.add_button = qtutils.create_toolbutton(icon=icon, tooltip=tooltip)
        self.refresh_button = qtutils.create_toolbutton(
            icon=icons.sync(), tooltip=N_('Refresh')
        )
        self.delete_button = qtutils.create_toolbutton(
            icon=icons.remove(), tooltip=N_('Delete')
        )
        self.close_button = qtutils.close_button()

        self._edit_button_layout = qtutils.vbox(
            defs.no_margin,
            defs.spacing,
            self.save_button,
            self.reset_button,
            qtutils.STRETCH,
        )
        self._edit_layout = qtutils.hbox(
            defs.no_margin, defs.spacing, self.editor, self._edit_button_layout
        )
        self._edit_widget = QtWidgets.QWidget()
        self._edit_widget.setLayout(self._edit_layout)

        self._left_buttons_layout = qtutils.hbox(
            defs.no_margin,
            defs.button_spacing,
            self.add_button,
            self.refresh_button,
            self.delete_button,
            qtutils.STRETCH,
        )
        self._left_layout = qtutils.vbox(
            defs.no_margin, defs.spacing, self._left_buttons_layout, self.forges
        )
        self._left_widget = QtWidgets.QWidget(self)
        self._left_widget.setLayout(self._left_layout)
        self._top_layout = qtutils.splitter(
            Qt.Horizontal, self._left_widget, self._edit_widget
        )
        width = self._top_layout.width()
        self._top_layout.setSizes([width // 4, width * 3 // 4])

        self._button_layout = qtutils.hbox(
            defs.margin,
            defs.spacing,
            qtutils.STRETCH,
            self.close_button,
        )
        self._layout = qtutils.vbox(
            defs.margin, defs.spacing, self._top_layout, self._button_layout
        )
        self.setLayout(self._layout)

        self.editor.forge_name.returnPressed.connect(self.save)
        self.editor.forge_url.returnPressed.connect(self.save)
        self.editor.forge_token.returnPressed.connect(self.save)
        self.editor.valid.connect(self.editor_validated)

        self.forges.itemChanged.connect(self.forge_name_changed)
        self.forges.itemSelectionChanged.connect(self.selection_changed)

        self.disable_editor()
        self.init_state(None, self.resize_widget, parent)
        self.forges.setFocus(Qt.OtherFocusReason)
        self.refresh()

        qtutils.connect_button(self.add_button, self.add)
        qtutils.connect_button(self.delete_button, self.delete)
        qtutils.connect_button(self.refresh_button, self.refresh)
        qtutils.connect_button(self.close_button, self.accept)
        qtutils.connect_button(self.save_button, self.save)
        qtutils.connect_button(self.reset_button, self.reset)
        qtutils.add_close_action(self)

    def reset(self):
        """Reset the forge data back to its saved values"""
        focus = self.focusWidget()
        if self.current_name:
            self.activate_forge(self.current_name)
        restore_focus(focus)

    @property
    def changed(self):
        """Have the forge details been edited?"""
        name = self.editor.name
        backend = self.editor.backend
        url = self.editor.url
        token = self.editor.token
        return (
            name != self.current_name
            or backend != self.current_backend
            or url != self.current_url
            or token != self.current_token
        )

    def save(self):
        """Save the forge details to disk"""
        if not self.changed:
            return
        context = self.context
        name = self.editor.name
        backend = self.editor.backend
        token = self.editor.token
        url = self.editor.url

        old_name = self.current_name
        old_backend = self.current_backend
        old_token = self.current_token
        old_url = self.current_url

        name_changed = name and name != old_name
        backend_changed = backend and backend != old_backend
        url_changed = url and url != old_url
        token_changed = token and token != old_token
        focus = self.focusWidget()

        name_ok = False
        backend_ok = False
        token_ok = False
        url_ok = False

        # Run the corresponding commands
        if name_changed or backend_changed or token_changed or url_changed:
            name_ok, backend_ok, token_ok, url_ok = cmds.do(
                cmds.ForgeUpdate, context, name, backend, token, url
            )
        if name_changed and old_name:
            cmds.do(cmds.ForgeDelete, context, old_name)

        # Update state if the change succeeded
        if backend_changed and backend_ok:
            self.current_backend = backend
        if token_changed and token_ok:
            self.current_token = token
        if url_changed and url_ok:
            self.current_url = url
        # A name change requires a refresh
        if name_changed and name_ok:
            self.current_name = name
            self.refresh(select=False)
            forges = utils.Sequence(self.forge_list)
            idx = forges.index(name)
            self.select_forge(idx)

        if name_changed or backend_changed or token_changed or url_changed:
            valid = self.editor.validate()
            self.editor_validated(valid)

        restore_focus(focus)

    def editor_validated(self, valid):
        """Respond to requests for form validation"""
        changed = self.changed
        self.reset_button.setEnabled(changed)
        self.save_button.setEnabled(changed and valid)

    def enable_editor(self, forge):
        """Enable the editor and update associated widgets"""
        self.activate_forge(forge)
        self.delete_button.setEnabled(True)

    def disable_editor(self):
        """Disable the editor"""
        self.save_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.update_editor(name='', token='', url='', enable=False)

    def resize_widget(self, parent):
        """Set the initial size of the widget"""
        width, height = qtutils.default_size(parent, 720, 445)
        self.resize(width, height)

    def select_forge(self, index):
        """Select a forge entry from an index"""
        if index >= 0:
            item = self.forges.item(index)
            if item:
                item.setSelected(True)

    def refresh(self, select=True):
        """Display the currently configured forges"""
        forges = gitcmds.get_forges(self.context)
        # Ignore notifications from self.forges while mutating.
        with qtutils.BlockSignals(self.forges):
            self.forges.clear()
            if forges:
                self.forges.addItems(forges)
            self.forge_list = forges

            for idx in range(len(forges)):
                item = self.forges.item(idx)
                item.setFlags(item.flags() | Qt.ItemIsEditable)

        if select and forges:
            if self.current_name:
                # Reselect the previously selected item
                forge_seq = utils.Sequence(forges)
                try:
                    idx = forge_seq.index(self.current_name)
                except ValueError:
                    idx = -1
                if idx >= 0:
                    item = self.forges.item(idx)
                    if item:
                        item.setSelected(True)
            else:
                # Nothing is selected; select the first item
                self.select_forge(0)

    def add(self):
        """Add a new forge"""
        # Calculate a default name for the new forge
        name = 'gitlab'
        url = 'https://gitlab.com'
        count = 2
        while name in self.forge_list:
            name = f'gitlab-{count}'
            url = f'https://gitlab-{count}.example.com'
            count += 1

        self.current_name = name
        self.current_backend = 'gitlab'
        self.current_token = ''
        self.current_url = url

        self.editor.name = name
        self.editor.backend = 'gitlab'
        self.editor.token = ''
        self.editor.url = url

        # Append the forge to the forge list and select it.
        self.forges.addItem(name)
        self.forge_list.append(name)
        self.select_forge(len(self.forge_list) - 1)

    def delete(self):
        """Delete the forge entry"""
        forge = qtutils.selected_item(self.forges, self.forge_list)
        if not forge:
            return
        cmds.do(cmds.ForgeDelete, self.context, forge)
        self.update_editor(name='', token='', url='', enable=False)
        self.refresh(select=True)

    def forge_name_changed(self, item):
        """The forge name has been changed"""
        idx = self.forges.row(item)
        if idx < 0:
            return
        if idx >= len(self.forge_list):
            return
        old_name = self.forge_list[idx]
        new_name = item.text()
        if new_name == old_name:
            return
        if not new_name:
            item.setText(old_name)
            return
        context = self.context
        ok = cmds.do(
            cmds.ForgeRename,
            context,
            old_name,
            new_name,
            self.editor.backend,
            self.editor.token,
            self.editor.url,
        )
        if ok:
            self.forge_list[idx] = new_name
            self.activate_forge(new_name)
        else:
            item.setText(old_name)

    def selection_changed(self):
        """Respond to changes to the forge list selection"""
        if self.changed:
            self.save()
        forge = qtutils.selected_item(self.forges, self.forge_list)
        if forge:
            self.enable_editor(forge)
        else:
            self.disable_editor()

    def activate_forge(self, name):
        """Start editing the forge entry"""
        backend = self.context.cfg.get(f'cola.forge.{name}.backend', default='gitlab')
        token = self.context.cfg.get(f'cola.forge.{name}.token', default='')
        url = self.context.cfg.get(f'cola.forge.{name}.url', default='')
        self.update_editor(name=name, backend=backend, token=token, url=url)

    def update_editor(self, name=None, backend=None, token=None, url=None, enable=True):
        """Update the editor and enable it for editing"""
        # These fields must be updated in this exact order otherwise
        # the editor will be seen as edited, which causes the Reset button
        # to re-enable itself via the valid() -> editor_validated() signal chain.
        if name is not None:
            self.current_name = name
            self.editor.name = name
        if backend is not None:
            if backend not in self.editor.forge_backend.values():
                self.editor.forge_backend.add_item(backend)
            self.current_backend = backend
            self.editor.backend = backend
        if token is not None:
            self.current_token = token
            self.editor.token = token
        if url is not None:
            self.current_url = url
            self.editor.url = url

        self.editor.setEnabled(enable)


def restore_focus(focus):
    """Restore focus to the current focus widget (e.g. when resetting values)"""
    if focus is None:
        return
    focus.setFocus(Qt.OtherFocusReason)
    if hasattr(focus, 'selectAll'):
        focus.selectAll()


class GitlabTokenValidator(QtGui.QValidator):
    """Validate github tokens. Currenlty only glpat-XXXXX tokens are accepted"""

    def validate(self, string, idx):
        """Validate the string"""
        new_string = ''
        glpat = 'glpat-'
        for c in string:
            if new_string == 'glpat' and c == '-':
                new_string += c
                continue
            if len(new_string) < len(glpat):
                if glpat.startswith(new_string + c):
                    new_string += c
                    continue
            if len(new_string) == 26:
                break
            if c.isalnum() or c == '_':
                new_string += c

        # Truncate to 26 characters.
        if len(new_string) == 26 and new_string.startswith('glpat-'):
            state = QtGui.QValidator.Acceptable
        elif new_string.startswith('glpat-'[0 : len(new_string)]):
            state = QtGui.QValidator.Intermediate
        else:
            state = QtGui.QValidator.Invalid
        return (state, new_string, idx)


class GenericTokenValidator(QtGui.QValidator):
    """Generic validator for validating tokens"""

    def validate(self, string, idx):
        new_string = ''
        for c in string:
            if c.isalnum() or c in ('-', '_'):
                new_string += c
        state = QtGui.QValidator.Acceptable
        return (state, new_string, idx)


class NameValidator(QtGui.QValidator):
    """Validator for forge names"""

    # Nb. this is the same as GenericTokenValidator but names must start with letters.

    def validate(self, string, idx):
        new_string = ''
        for i, c in enumerate(string):
            if i == 0:
                if c.isalpha():
                    new_string += c
                else:
                    idx -= 1
            elif c.isalnum() or c in ('-', '_'):
                new_string += c
            else:
                idx -= 1
        state = QtGui.QValidator.Acceptable
        return (state, new_string, idx)


class Backend:
    GITLAB = 'gitlab'
    VALIDATORS = {
        GITLAB: GitlabTokenValidator,
    }

    @classmethod
    def get_validator(cls, widget, backend):
        """Return the validator for the specified backend"""
        validator_cls = cls.VALIDATORS.get(backend, GenericTokenValidator)
        return validator_cls(widget)


class ForgeEditorWidget(QtWidgets.QWidget):
    """Enable details for a forge"""

    name = property(
        lambda self: self.forge_name.value(),
        lambda self, value: self.forge_name.set_value(value),
    )
    backend = property(
        lambda self: self.forge_backend.value(),
        lambda self, value: self.set_backend(value),
    )
    token = property(
        lambda self: get(self.forge_token),
        lambda self, value: self.forge_token.set_value(value),
    )
    url = property(
        lambda self: get(self.forge_url),
        lambda self, value: self.forge_url.set_value(value),
    )
    valid = Signal(bool)

    def __init__(self, context, parent, readonly=False):
        super().__init__(parent)
        self.setWindowModality(Qt.WindowModal)
        self.context = context
        self.forge_name = lineedit(context, N_('Name for this forge entry'))
        self.forge_backend = qtutils.combo(
            list(Backend.VALIDATORS), tooltip=N_('Forge backend'), parent=self
        )
        self.forge_url = lineedit(context, 'Forge URL (example: https://gitlab.com)')
        self.forge_token = lineedit(context, N_('API token for accessing the forge'))
        self.forge_token.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.display_token_button = qtutils.create_toolbutton_with_callback(
            self._toggle_display_token,
            '',
            icons.visualize(),
            N_('Display API token'),
        )
        self.forge_token_layout = qtutils.hbox(
            defs.margin, defs.spacing, self.display_token_button, self.forge_token
        )

        self._form = qtutils.form(
            defs.margin,
            defs.spacing,
            (N_('Backend'), self.forge_backend),
            (N_('Name'), self.forge_name),
            (N_('URL'), self.forge_url),
            (N_('API Token'), self.forge_token_layout),
        )

        self._layout = qtutils.vbox(defs.margin, defs.spacing, self._form)
        self.setLayout(self._layout)

        self.forge_name.setValidator(NameValidator(self.forge_name))
        self.forge_name.textChanged.connect(self.validate)
        self.forge_token.textChanged.connect(self.validate)
        self.forge_url.textChanged.connect(self.validate)
        if readonly:
            self.forge_name.setReadOnly(True)
            self.forge_backend.setReadOnly(True)
            self.forge_url.setReadOnly(True)
            self.forge_token.setReadOnly(True)

    def validate(self, _text=''):
        """Validate the form and emit signals to with the validation state"""
        name = self.name
        url = self.url
        token = self.token
        valid = bool(name) and bool(token) and bool(url)
        self.valid.emit(valid)
        return valid

    def set_backend(self, backend):
        """Set a validator based on the backend"""
        self.forge_backend.set_value(backend)
        self.forge_token.setValidator(Backend.get_validator(self, backend))

    def _toggle_display_token(self):
        """Toggle the display of tokens"""
        current_mode = self.forge_token.echoMode()
        if current_mode == QtWidgets.QLineEdit.EchoMode.Password:
            new_mode = QtWidgets.QLineEdit.EchoMode.Normal
        else:
            new_mode = QtWidgets.QLineEdit.EchoMode.Password
        self.forge_token.setEchoMode(new_mode)
