"""
PySide6 compatibility layer.
On Windows desktops with PySide6 installed, exports native PySide6 classes directly.
In headless test environments without PySide6 installed, provides a functional Qt
object/signal/thread/widget model so all workers, table models, and 12 UI pages
can be instantiated, wired, and tested end-to-end.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, List, Optional

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import (
        QAbstractTableModel,
        QModelIndex,
        QObject,
        QPoint,
        QRect,
        QRectF,
        QSize,
        Qt,
        QThread,
        QTimer,
        QUrl,
        Signal,
        Slot,
    )
    from PySide6.QtGui import (
        QAction,
        QBrush,
        QColor,
        QDesktopServices,
        QFont,
        QIcon,
        QKeySequence,
        QPainter,
        QPen,
        QPixmap,
        QShortcut,
    )
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QSplitter,
        QStackedWidget,
        QStatusBar,
        QStyle,
        QTabWidget,
        QTableView,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QToolBar,
        QToolButton,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False

    class _BoundSignal:
        def __init__(self) -> None:
            self._slots: List[Callable[..., Any]] = []

        def connect(self, slot: Callable[..., Any]) -> None:
            if slot not in self._slots:
                self._slots.append(slot)

        def disconnect(self, slot: Optional[Callable[..., Any]] = None) -> None:
            if slot is None:
                self._slots.clear()
            elif slot in self._slots:
                self._slots.remove(slot)

        def emit(self, *args: Any, **kwargs: Any) -> None:
            for s in list(self._slots):
                s(*args, **kwargs)

    class Signal:  # type: ignore
        def __init__(self, *types: Any) -> None:
            self._types = types
            self._name = ""

        def __set_name__(self, owner: Any, name: str) -> None:
            self._name = f"_sig_{name}"

        def __get__(self, instance: Any, owner: Any = None) -> Any:
            if instance is None:
                return self
            sig = getattr(instance, self._name, None)
            if sig is None:
                sig = _BoundSignal()
                setattr(instance, self._name, sig)
            return sig

    def Slot(*types: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:  # type: ignore
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn
        return decorator

    class Qt:  # type: ignore
        DisplayRole = 0
        DecorationRole = 1
        EditRole = 2
        ToolTipRole = 3
        TextAlignmentRole = 7
        ForegroundRole = 9
        UserRole = 256
        Horizontal = 1
        Vertical = 2
        AlignLeft = 0x0001
        AlignRight = 0x0002
        AlignHCenter = 0x0004
        AlignVCenter = 0x0080
        AlignCenter = AlignHCenter | AlignVCenter
        PointingHandCursor = 13
        CustomContextMenu = 3
        ascendingOrder = 0
        AscendingOrder = 0
        DescendingOrder = 1
        NoPen = 0
        SolidLine = 1
        KeepAspectRatio = 1
        SmoothTransformation = 1
        ItemIsEnabled = 1
        ItemIsSelectable = 2
        ItemIsUserCheckable = 16
        Checked = 2
        Unchecked = 0
        Key_Delete = 0x01000007
        Key_F2 = 0x01000031
        Key_F5 = 0x01000034
        Key_Backspace = 0x01000003

    class QObject:  # type: ignore
        def __init__(self, parent: Any = None) -> None:
            self._parent = parent

    class QThread(QObject):  # type: ignore
        started = Signal()
        finished = Signal()

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._thread: Optional[threading.Thread] = None
            self._running = False

        def start(self) -> None:
            self._running = True
            self.started.emit()
            self._thread = threading.Thread(target=self._run_wrapper, daemon=True)
            self._thread.start()

        def _run_wrapper(self) -> None:
            try:
                self.run()
            finally:
                self._running = False
                self.finished.emit()

        def run(self) -> None:
            pass

        def isRunning(self) -> bool:
            return self._running

        def wait(self, msecs: int = 5000) -> bool:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=msecs / 1000.0)
            return not self._running

    class QModelIndex:  # type: ignore
        def __init__(self, row: int = -1, col: int = -1, valid: bool = False) -> None:
            self._row = row
            self._col = col
            self._valid = valid

        def isValid(self) -> bool:
            return self._valid

        def row(self) -> int:
            return self._row

        def column(self) -> int:
            return self._col

    class QAbstractTableModel(QObject):  # type: ignore
        layoutChanged = Signal()

        def beginResetModel(self) -> None:
            pass

        def endResetModel(self) -> None:
            self.layoutChanged.emit()

        def index(self, row: int, col: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
            return QModelIndex(row, col, True)

        def headerData(self, section: int, orientation: int, role: int = Qt.DisplayRole) -> Any:
            return None

    class QWidget(QObject):  # type: ignore
        customContextMenuRequested = Signal(object)

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._layout: Any = None
            self._visible = True
            self._style = ""
            self._title = ""
            self._tooltip = ""

        def setLayout(self, layout: Any) -> None:
            self._layout = layout

        def layout(self) -> Any:
            return self._layout

        def setStyleSheet(self, qss: str) -> None:
            self._style = qss

        def styleSheet(self) -> str:
            return self._style

        def setWindowTitle(self, title: str) -> None:
            self._title = title

        def windowTitle(self) -> str:
            return self._title

        def setMinimumSize(self, *args: Any) -> None:
            pass

        def setMinimumWidth(self, w: int) -> None:
            pass

        def setMaximumWidth(self, w: int) -> None:
            pass

        def setFixedHeight(self, h: int) -> None:
            pass

        def setFixedSize(self, *args: Any) -> None:
            pass

        def setCursor(self, *args: Any) -> None:
            pass

        def setToolTip(self, tip: str) -> None:
            self._tooltip = tip

        def setContextMenuPolicy(self, *args: Any) -> None:
            pass

        def setSizePolicy(self, *args: Any) -> None:
            pass

        def setObjectName(self, name: str) -> None:
            self._obj_name = name

        def show(self) -> None:
            self._visible = True

        def hide(self) -> None:
            self._visible = False

        def setVisible(self, v: bool) -> None:
            self._visible = v

        def isVisible(self) -> bool:
            return self._visible

        def update(self) -> None:
            pass

        def width(self) -> int:
            return 800

        def height(self) -> int:
            return 500

        def resize(self, *args: Any) -> None:
            pass

    class QFrame(QWidget):  # type: ignore
        NoFrame = 0
        StyledPanel = 1
        HLine = 4

        def setFrameShape(self, *args: Any) -> None:
            pass

    class QMainWindow(QWidget):  # type: ignore
        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._central: Optional[QWidget] = None
            self._statusbar: Any = None

        def setCentralWidget(self, w: QWidget) -> None:
            self._central = w

        def centralWidget(self) -> Optional[QWidget]:
            return self._central

        def setStatusBar(self, sb: Any) -> None:
            self._statusbar = sb

        def statusBar(self) -> Any:
            if not self._statusbar:
                self._statusbar = QStatusBar()
            return self._statusbar

    class _BaseLayout:
        def __init__(self, parent: Any = None) -> None:
            self.items: List[Any] = []
            if parent is not None and hasattr(parent, "setLayout"):
                parent.setLayout(self)

        def addWidget(self, w: Any, *args: Any, **kwargs: Any) -> None:
            self.items.append(w)

        def addLayout(self, l: Any, *args: Any) -> None:
            self.items.append(l)

        def addStretch(self, *args: Any) -> None:
            pass

        def addSpacing(self, *args: Any) -> None:
            pass

        def setContentsMargins(self, *args: Any) -> None:
            pass

        def setSpacing(self, *args: Any) -> None:
            pass

        def count(self) -> int:
            return len(self.items)

    class QVBoxLayout(_BaseLayout):  # type: ignore
        pass

    class QHBoxLayout(_BaseLayout):  # type: ignore
        pass

    class QGridLayout(_BaseLayout):  # type: ignore
        pass

    class QFormLayout(_BaseLayout):  # type: ignore
        def addRow(self, label: Any, field: Any = None) -> None:
            self.items.append((label, field))

    class QLabel(QWidget):  # type: ignore
        def __init__(self, text: str = "", parent: Any = None) -> None:
            super().__init__(parent)
            self._text = str(text)

        def setText(self, text: str) -> None:
            self._text = str(text)

        def text(self) -> str:
            return self._text

        def setAlignment(self, *args: Any) -> None:
            pass

        def setWordWrap(self, *args: Any) -> None:
            pass

        def setPixmap(self, *args: Any) -> None:
            pass

    class QPushButton(QWidget):  # type: ignore
        clicked = Signal()

        def __init__(self, text: str = "", parent: Any = None) -> None:
            super().__init__(parent)
            self._text = text
            self._checkable = False
            self._checked = False
            self._enabled = True

        def setText(self, t: str) -> None:
            self._text = t

        def text(self) -> str:
            return self._text

        def setCheckable(self, c: bool) -> None:
            self._checkable = c

        def setChecked(self, c: bool) -> None:
            self._checked = c

        def isChecked(self) -> bool:
            return self._checked

        def setEnabled(self, e: bool) -> None:
            self._enabled = e

        def isEnabled(self) -> bool:
            return self._enabled

        def click(self) -> None:
            self.clicked.emit()

    class QToolButton(QPushButton):  # type: ignore
        pass

    class QLineEdit(QWidget):  # type: ignore
        textChanged = Signal(str)
        returnPressed = Signal()

        def __init__(self, text: str = "", parent: Any = None) -> None:
            super().__init__(parent)
            self._text = text

        def setText(self, t: str) -> None:
            self._text = str(t)
            self.textChanged.emit(self._text)

        def text(self) -> str:
            return self._text

        def setPlaceholderText(self, p: str) -> None:
            self._placeholder = p

        def setReadOnly(self, ro: bool) -> None:
            self._ro = ro

        def setFocus(self) -> None:
            pass

        def selectAll(self) -> None:
            pass

    class QComboBox(QWidget):  # type: ignore
        currentTextChanged = Signal(str)
        currentIndexChanged = Signal(int)

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._items: List[str] = []
            self._idx = 0

        def addItem(self, text: str, userData: Any = None) -> None:
            self._items.append(str(text))

        def addItems(self, texts: List[str]) -> None:
            for t in texts:
                self.addItem(t)

        def clear(self) -> None:
            self._items.clear()
            self._idx = 0

        def currentText(self) -> str:
            if 0 <= self._idx < len(self._items):
                return self._items[self._idx]
            return ""

        def setCurrentText(self, text: str) -> None:
            if text in self._items:
                self._idx = self._items.index(text)
                self.currentTextChanged.emit(text)

        def setCurrentIndex(self, idx: int) -> None:
            if 0 <= idx < len(self._items):
                self._idx = idx
                self.currentIndexChanged.emit(idx)
                self.currentTextChanged.emit(self._items[idx])

        def count(self) -> int:
            return len(self._items)

    class QCheckBox(QPushButton):  # type: ignore
        stateChanged = Signal(int)

        def setChecked(self, c: bool) -> None:
            super().setChecked(c)
            self.stateChanged.emit(Qt.Checked if c else Qt.Unchecked)

    class QSpinBox(QWidget):  # type: ignore
        valueChanged = Signal(int)

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._val = 0

        def setRange(self, low: int, high: int) -> None:
            pass

        def setMinimum(self, low: int) -> None:
            pass

        def setMaximum(self, high: int) -> None:
            pass

        def setSuffix(self, s: str) -> None:
            pass

        def setValue(self, v: int) -> None:
            self._val = int(v)
            self.valueChanged.emit(self._val)

        def value(self) -> int:
            return self._val

    class QProgressBar(QWidget):  # type: ignore
        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._val = 0

        def setRange(self, low: int, high: int) -> None:
            pass

        def setValue(self, v: int) -> None:
            self._val = v

        def value(self) -> int:
            return self._val

        def setTextVisible(self, v: bool) -> None:
            pass

        def setFormat(self, fmt: str) -> None:
            pass

    class QStackedWidget(QWidget):  # type: ignore
        currentChanged = Signal(int)

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._widgets: List[QWidget] = []
            self._idx = 0

        def addWidget(self, w: QWidget) -> int:
            self._widgets.append(w)
            return len(self._widgets) - 1

        def setCurrentIndex(self, idx: int) -> None:
            if 0 <= idx < len(self._widgets):
                self._idx = idx
                self.currentChanged.emit(idx)

        def setCurrentWidget(self, w: QWidget) -> None:
            if w in self._widgets:
                self.setCurrentIndex(self._widgets.index(w))

        def currentIndex(self) -> int:
            return self._idx

        def currentWidget(self) -> Optional[QWidget]:
            return self._widgets[self._idx] if self._widgets else None

        def count(self) -> int:
            return len(self._widgets)

    class QTabWidget(QWidget):  # type: ignore
        currentChanged = Signal(int)
        tabCloseRequested = Signal(int)

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._tabs: List[tuple[QWidget, str]] = []
            self._idx = 0

        def addTab(self, widget: QWidget, label: str) -> int:
            self._tabs.append((widget, label))
            self._idx = len(self._tabs) - 1
            return self._idx

        def removeTab(self, idx: int) -> None:
            if 0 <= idx < len(self._tabs):
                self._tabs.pop(idx)
                self._idx = max(0, min(self._idx, len(self._tabs) - 1))

        def count(self) -> int:
            return len(self._tabs)

        def currentIndex(self) -> int:
            return self._idx

        def setCurrentIndex(self, idx: int) -> None:
            if 0 <= idx < len(self._tabs):
                self._idx = idx
                self.currentChanged.emit(idx)

        def currentWidget(self) -> Optional[QWidget]:
            return self._tabs[self._idx][0] if self._tabs else None

        def widget(self, idx: int) -> Optional[QWidget]:
            return self._tabs[idx][0] if 0 <= idx < len(self._tabs) else None

        def setTabText(self, idx: int, text: str) -> None:
            if 0 <= idx < len(self._tabs):
                w, _ = self._tabs[idx]
                self._tabs[idx] = (w, text)

        def setTabsClosable(self, c: bool) -> None:
            pass

        def setMovable(self, m: bool) -> None:
            pass

    class QSplitter(QWidget):  # type: ignore
        def __init__(self, orientation: int = Qt.Horizontal, parent: Any = None) -> None:
            super().__init__(parent)
            self._children: List[QWidget] = []

        def addWidget(self, w: QWidget) -> None:
            self._children.append(w)

        def setSizes(self, sizes: List[int]) -> None:
            pass

        def setStretchFactor(self, idx: int, stretch: int) -> None:
            pass

    class QScrollArea(QWidget):  # type: ignore
        def setWidgetResizable(self, r: bool) -> None:
            pass

        def setWidget(self, w: QWidget) -> None:
            self._w = w

    class QGroupBox(QWidget):  # type: ignore
        def __init__(self, title: str = "", parent: Any = None) -> None:
            super().__init__(parent)
            self._title = title

    class QHeaderView:  # type: ignore
        Stretch = 1
        ResizeToContents = 3
        Interactive = 0

        def setSectionResizeMode(self, *args: Any) -> None:
            pass

        def setStretchLastSection(self, *args: Any) -> None:
            pass

    class QAbstractItemView:  # type: ignore
        SelectRows = 1
        ExtendedSelection = 3
        SingleSelection = 1
        NoEditTriggers = 0

    class _SelectionModel:
        def selectedRows(self) -> List[QModelIndex]:
            return []

    class QTableView(QWidget):  # type: ignore
        doubleClicked = Signal(QModelIndex)
        clicked = Signal(QModelIndex)

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._model: Any = None
            self._header = QHeaderView()

        def setModel(self, model: Any) -> None:
            self._model = model

        def model(self) -> Any:
            return self._model

        def horizontalHeader(self) -> QHeaderView:
            return self._header

        def verticalHeader(self) -> Any:
            class _VH:
                def setVisible(self, v: bool) -> None:
                    pass
                def setDefaultSectionSize(self, s: int) -> None:
                    pass
            return _VH()

        def setSelectionBehavior(self, *args: Any) -> None:
            pass

        def setSelectionMode(self, *args: Any) -> None:
            pass

        def setSortingEnabled(self, *args: Any) -> None:
            pass

        def setAlternatingRowColors(self, *args: Any) -> None:
            pass

        def setShowGrid(self, *args: Any) -> None:
            pass

        def selectionModel(self) -> _SelectionModel:
            return _SelectionModel()

        def indexAt(self, pos: Any) -> QModelIndex:
            return QModelIndex()

    class QTableWidgetItem:  # type: ignore
        def __init__(self, text: str = "") -> None:
            self._text = str(text)
            self._data: dict = {}
            self._check = Qt.Unchecked

        def text(self) -> str:
            return self._text

        def setText(self, t: str) -> None:
            self._text = str(t)

        def setData(self, role: int, value: Any) -> None:
            self._data[role] = value

        def data(self, role: int) -> Any:
            return self._data.get(role)

        def setCheckState(self, state: int) -> None:
            self._check = state

        def checkState(self) -> int:
            return self._check

        def setFlags(self, flags: int) -> None:
            pass

    class QTableWidget(QTableView):  # type: ignore
        itemDoubleClicked = Signal(QTableWidgetItem)
        itemClicked = Signal(QTableWidgetItem)

        def __init__(self, rows: int = 0, cols: int = 0, parent: Any = None) -> None:
            super().__init__(parent)
            self._rows = rows
            self._cols = cols
            self._cells: dict = {}

        def setColumnCount(self, cols: int) -> None:
            self._cols = cols

        def setRowCount(self, rows: int) -> None:
            self._rows = rows

        def rowCount(self) -> int:
            return self._rows

        def columnCount(self) -> int:
            return self._cols

        def setHorizontalHeaderLabels(self, labels: List[str]) -> None:
            self._headers = labels

        def setItem(self, row: int, col: int, item: QTableWidgetItem) -> None:
            self._cells[(row, col)] = item

        def item(self, row: int, col: int) -> Optional[QTableWidgetItem]:
            return self._cells.get((row, col))

        def setEditTriggers(self, *args: Any) -> None:
            pass

        def clearContents(self) -> None:
            self._cells.clear()

        def currentRow(self) -> int:
            return 0 if self._rows > 0 else -1

    class QTreeWidgetItem:  # type: ignore
        def __init__(self, parent_or_strings: Any = None, strings: Optional[List[str]] = None) -> None:
            if isinstance(parent_or_strings, list):
                self._texts = [str(s) for s in parent_or_strings]
            elif strings is not None:
                self._texts = [str(s) for s in strings]
                if hasattr(parent_or_strings, "addChild"):
                    parent_or_strings.addChild(self)
                elif hasattr(parent_or_strings, "addTopLevelItem"):
                    parent_or_strings.addTopLevelItem(self)
            else:
                self._texts = []
            self._children: List[QTreeWidgetItem] = []
            self._data: dict = {}
            self._check = Qt.Unchecked

        def setText(self, col: int, text: str) -> None:
            while len(self._texts) <= col:
                self._texts.append("")
            self._texts[col] = str(text)

        def text(self, col: int) -> str:
            return self._texts[col] if col < len(self._texts) else ""

        def addChild(self, child: "QTreeWidgetItem") -> None:
            self._children.append(child)

        def childCount(self) -> int:
            return len(self._children)

        def child(self, idx: int) -> "QTreeWidgetItem":
            return self._children[idx]

        def setData(self, col: int, role: int, val: Any) -> None:
            self._data[(col, role)] = val

        def data(self, col: int, role: int) -> Any:
            return self._data.get((col, role))

        def setCheckState(self, col: int, state: int) -> None:
            self._check = state

        def checkState(self, col: int) -> int:
            return self._check

        def setExpanded(self, exp: bool) -> None:
            pass

    class QTreeWidget(QWidget):  # type: ignore
        itemDoubleClicked = Signal(QTreeWidgetItem, int)
        itemClicked = Signal(QTreeWidgetItem, int)

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._items: List[QTreeWidgetItem] = []
            self._header = QHeaderView()

        def setHeaderLabels(self, labels: List[str]) -> None:
            self._headers = labels

        def header(self) -> QHeaderView:
            return self._header

        def addTopLevelItem(self, item: QTreeWidgetItem) -> None:
            self._items.append(item)

        def topLevelItemCount(self) -> int:
            return len(self._items)

        def topLevelItem(self, idx: int) -> QTreeWidgetItem:
            return self._items[idx]

        def clear(self) -> None:
            self._items.clear()

        def expandAll(self) -> None:
            pass

    class QListWidgetItem:  # type: ignore
        def __init__(self, text: str = "") -> None:
            self._text = text
            self._data: dict = {}

        def text(self) -> str:
            return self._text

        def setData(self, role: int, val: Any) -> None:
            self._data[role] = val

        def data(self, role: int) -> Any:
            return self._data.get(role)

    class QListWidget(QWidget):  # type: ignore
        itemClicked = Signal(QListWidgetItem)
        currentRowChanged = Signal(int)

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self._items: List[QListWidgetItem] = []

        def addItem(self, item: Any) -> None:
            if isinstance(item, str):
                item = QListWidgetItem(item)
            self._items.append(item)

        def clear(self) -> None:
            self._items.clear()

        def count(self) -> int:
            return len(self._items)

    class QPlainTextEdit(QWidget):  # type: ignore
        def __init__(self, text: str = "", parent: Any = None) -> None:
            super().__init__(parent)
            self._text = text

        def setPlainText(self, text: str) -> None:
            self._text = str(text)

        def toPlainText(self) -> str:
            return self._text

        def setReadOnly(self, ro: bool) -> None:
            pass

    class QTextEdit(QPlainTextEdit):  # type: ignore
        def setHtml(self, html: str) -> None:
            self._text = html

    class QStatusBar(QWidget):  # type: ignore
        def showMessage(self, msg: str, timeout: int = 0) -> None:
            self._msg = msg

    class QMenu(QWidget):  # type: ignore
        def addAction(self, text_or_act: Any, callback: Any = None) -> Any:
            act = QAction(str(text_or_act), self)
            if callback:
                act.triggered.connect(callback)
            return act

        def addSeparator(self) -> None:
            pass

        def exec(self, *args: Any) -> Any:
            return None

    class QAction(QObject):  # type: ignore
        triggered = Signal()

        def __init__(self, text: str = "", parent: Any = None) -> None:
            super().__init__(parent)
            self._text = text

        def setShortcut(self, *args: Any) -> None:
            pass

    class QShortcut(QObject):  # type: ignore
        activated = Signal()

        def __init__(self, seq: Any, parent: Any = None) -> None:
            super().__init__(parent)

    class QKeySequence:  # type: ignore
        def __init__(self, seq: Any) -> None:
            self.seq = seq

    class QColor:  # type: ignore
        def __init__(self, *args: Any) -> None:
            self.args = args

    class QPen:  # type: ignore
        def __init__(self, *args: Any) -> None:
            pass

    class QBrush:  # type: ignore
        def __init__(self, *args: Any) -> None:
            pass

    class QFont:  # type: ignore
        Bold = 75
        def __init__(self, *args: Any) -> None:
            pass
        def setBold(self, b: bool) -> None:
            pass
        def setPointSize(self, s: int) -> None:
            pass

    class QPainter:  # type: ignore
        Antialiasing = 1
        def __init__(self, *args: Any) -> None:
            pass
        def setRenderHint(self, *args: Any) -> None:
            pass
        def setPen(self, *args: Any) -> None:
            pass
        def setBrush(self, *args: Any) -> None:
            pass
        def setFont(self, *args: Any) -> None:
            pass
        def drawRect(self, *args: Any) -> None:
            pass
        def drawRoundedRect(self, *args: Any) -> None:
            pass
        def drawPie(self, *args: Any) -> None:
            pass
        def drawEllipse(self, *args: Any) -> None:
            pass
        def drawText(self, *args: Any) -> None:
            pass
        def end(self) -> None:
            pass

    class QPixmap:  # type: ignore
        def __init__(self, *args: Any) -> None:
            self._null = False
        def isNull(self) -> bool:
            return self._null
        def scaled(self, *args: Any) -> "QPixmap":
            return self

    class QIcon:  # type: ignore
        def __init__(self, *args: Any) -> None:
            pass

    class QRect:  # type: ignore
        def __init__(self, x: int = 0, y: int = 0, w: int = 100, h: int = 100) -> None:
            self.x, self.y, self.w, self.h = x, y, w, h

    class QRectF:  # type: ignore
        def __init__(self, x: float = 0, y: float = 0, w: float = 100, h: float = 100) -> None:
            self._x, self._y, self._w, self._h = float(x), float(y), float(w), float(h)
        def x(self) -> float: return self._x
        def y(self) -> float: return self._y
        def width(self) -> float: return self._w
        def height(self) -> float: return self._h
        def contains(self, pt: Any) -> bool:
            px = getattr(pt, "x", lambda: 0)()
            py = getattr(pt, "y", lambda: 0)()
            return self._x <= px <= self._x + self._w and self._y <= py <= self._y + self._h
        def adjusted(self, dx1: float, dy1: float, dx2: float, dy2: float) -> "QRectF":
            return QRectF(self._x + dx1, self._y + dy1, self._w + (dx2 - dx1), self._h + (dy2 - dy1))

    class QSize:  # type: ignore
        def __init__(self, w: int = 0, h: int = 0) -> None:
            self.w, self.h = w, h

    class QPoint:  # type: ignore
        def __init__(self, x: int = 0, y: int = 0) -> None:
            self._x, self._y = x, y
        def x(self) -> int: return self._x
        def y(self) -> int: return self._y

    class QUrl:  # type: ignore
        @staticmethod
        def fromLocalFile(p: str) -> str:
            return p

    class QDesktopServices:  # type: ignore
        @staticmethod
        def openUrl(url: Any) -> bool:
            return True

    class QMessageBox:  # type: ignore
        Yes = 16384
        No = 65536
        @staticmethod
        def information(*args: Any) -> int:
            return QMessageBox.Yes
        @staticmethod
        def warning(*args: Any) -> int:
            return QMessageBox.Yes
        @staticmethod
        def critical(*args: Any) -> int:
            return QMessageBox.Yes
        @staticmethod
        def question(*args: Any) -> int:
            return QMessageBox.Yes

    class QFileDialog:  # type: ignore
        @staticmethod
        def getExistingDirectory(*args: Any) -> str:
            return ""
        @staticmethod
        def getSaveFileName(*args: Any) -> tuple[str, str]:
            return ("", "")

    class QInputDialog:  # type: ignore
        @staticmethod
        def getText(*args: Any, **kwargs: Any) -> tuple[str, bool]:
            return ("", False)

    class QSizePolicy:  # type: ignore
        Expanding = 7
        Preferred = 5
        Fixed = 0

    class QTimer(QObject):  # type: ignore
        timeout = Signal()
        def start(self, ms: int = 1000) -> None:
            pass
        def stop(self) -> None:
            pass
        @staticmethod
        def singleShot(ms: int, fn: Callable[[], None]) -> None:
            fn()

    class QApplication:  # type: ignore
        _inst: Optional["QApplication"] = None
        def __init__(self, argv: Optional[List[str]] = None) -> None:
            QApplication._inst = self
        @staticmethod
        def instance() -> Optional["QApplication"]:
            return QApplication._inst
        def setApplicationName(self, name: str) -> None:
            pass
        def setOrganizationName(self, name: str) -> None:
            pass
        def setStyleSheet(self, qss: str) -> None:
            pass
        @staticmethod
        def clipboard() -> Any:
            class _Clip:
                _txt = ""
                def setText(self, t: str) -> None:
                    _Clip._txt = t
                def text(self) -> str:
                    return _Clip._txt
            return _Clip()
        def exec(self) -> int:
            return 0
