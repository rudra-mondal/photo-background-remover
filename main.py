"""
A complete GUI application for background removal using rembg.
Features:
  - Open image via menu or drag & drop.
  - Display original image and processed (background removed) image side by side.
  - Zoom and pan for both images.
  - Advanced settings for alpha matting.
  - Save the processed image in full resolution.
  - Visually appealing interface with menus and styling.
"""

import sys, io
from rembg import remove
from PIL import Image
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QHBoxLayout, QVBoxLayout,
    QPushButton, QFileDialog, QAction, QDialog, QFormLayout, QCheckBox,
    QSpinBox, QDialogButtonBox, QMessageBox, QSizePolicy
)
from PyQt5.QtGui import QPixmap, QDragEnterEvent, QDropEvent, QCursor, QTextCursor, QTextCharFormat, QFont
from PyQt5.QtCore import Qt, QPointF, QRectF, QSize, QUrl

# ----- Settings Dialog for Advanced Options -----
class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Settings")
        self.setModal(True)
        self.settings = settings if settings else {
            "alpha_matting": False,
            "foreground_threshold": 240,
            "foreground_threshold": 240,
            "background_threshold": 10,
            "erode_size": 10
        }
        self.init_ui()

    def init_ui(self):
        layout = QFormLayout(self)

        # Alpha matting option
        self.alpha_matting_cb = QCheckBox("Enable Alpha Matting")
        self.alpha_matting_cb.setChecked(self.settings["alpha_matting"])
        layout.addRow("Alpha Matting:", self.alpha_matting_cb)

        # Foreground threshold spin box
        self.foreground_sb = QSpinBox()
        self.foreground_sb.setRange(0, 255)
        self.foreground_sb.setValue(self.settings["foreground_threshold"])
        layout.addRow("Foreground Threshold:", self.foreground_sb)

        # Background threshold spin box
        self.background_sb = QSpinBox()
        self.background_sb.setRange(0, 255)
        self.background_sb.setValue(self.settings["background_threshold"])
        layout.addRow("Background Threshold:", self.background_sb)

        # Erode size spin box
        self.erode_sb = QSpinBox()
        self.erode_sb.setRange(0, 50)
        self.erode_sb.setValue(self.settings["erode_size"])
        layout.addRow("Erode Size:", self.erode_sb)

        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def getSettings(self):
        return {
            "alpha_matting": self.alpha_matting_cb.isChecked(),
            "foreground_threshold": self.foreground_sb.value(),
            "background_threshold": self.background_sb.value(),
            "erode_size": self.erode_sb.value()
        }

# ----- Custom QLabel to Support Drag & Drop, Zoom & Pan with Fixed Scaling -----
class ImageLabel(QLabel):
    def __init__(self, text="Drag and drop an image here", main_window=None, is_original=False): # Added is_original flag
        super().__init__()
        self.setText(text)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 10px;
                font-size: 14px;
                color: #555;
                padding: 10px;
            }
        """)
        self.setAcceptDrops(True)
        self.file_path = None
        self.original_pixmap = None
        self.main_window = main_window
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.is_original_label = is_original # Store if this is original label

        self.zoom_factor = 1.0
        self.fit_zoom_factor = 1.0 # Initialize fit zoom factor
        self.pan_offset = QPointF(0, 0)
        self.is_panning = False
        self.last_pan_point = QPointF()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self.is_original_label: # Accept drop only for original label
            if event.mimeData().hasUrls():
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        if self.is_original_label: # Process drop only for original label
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                loaded_path = self.loadImage(file_path)
                if loaded_path:
                    if self.main_window and hasattr(self.main_window, '_load_raw_image_data'):
                        self.main_window._load_raw_image_data(loaded_path)

    def loadImage(self, file_path):
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Error", "Cannot load image!")
            return None
        self.file_path = file_path
        self.original_pixmap = pixmap
        self.calculate_fit_zoom() # Calculate fit zoom factor
        self.zoom_factor = self.fit_zoom_factor # Initially fit image
        self.pan_offset = QPointF(0,0) # reset pan offset when loading new image
        self.updatePixmap()
        return file_path

    def updatePixmap(self):
        if self.original_pixmap:
            scaled_pixmap = self.original_pixmap.scaled(
                int(self.original_pixmap.width() * self.zoom_factor),
                int(self.original_pixmap.height() * self.zoom_factor),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            offset_x = self.pan_offset.x()
            offset_y = self.pan_offset.y()

            # Clamp pan offset to image boundaries
            max_offset_x = max(0, scaled_pixmap.width() - self.width())
            max_offset_y = max(0, scaled_pixmap.height() - self.height())
            offset_x = max(-max_offset_x, min(offset_x, 0)) if max_offset_x > 0 else 0
            offset_y = max(-max_offset_y, min(offset_y, 0)) if max_offset_y > 0 else 0

            self.pan_offset = QPointF(offset_x, offset_y) # Update pan_offset with clamped values

            target_rect = QRectF(-offset_x, -offset_y, self.width(), self.height()) # Target rect from clamped offset
            source_rect = QRectF(0, 0, scaled_pixmap.width(), scaled_pixmap.height())

            intersect_rect = target_rect.intersected(source_rect)
            if not intersect_rect.isEmpty():
                cropped_pixmap = scaled_pixmap.copy(intersect_rect.toRect())
                self.setPixmap(cropped_pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)) # Scale to label size after crop
            else:
                self.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.calculate_fit_zoom()
        self.updatePixmap()

    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor

        old_zoom = self.zoom_factor
        if event.angleDelta().y() > 0:
            self.zoom_factor *= zoom_in_factor
        else:
            self.zoom_factor *= zoom_out_factor

        self.zoom_factor = max(self.fit_zoom_factor, min(self.zoom_factor, 10.0))

        if self.zoom_factor != old_zoom:
            self.updatePixmap()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_panning = True
            self.last_pan_point = event.pos()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.is_panning:
            delta = event.pos() - self.last_pan_point
            self.pan_offset += QPointF(delta.x(), delta.y())
            self.last_pan_point = event.pos()
            self.updatePixmap()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_panning = False
            self.setCursor(Qt.ArrowCursor)

    def reset_zoom_pan(self):
        self.zoom_factor = self.fit_zoom_factor
        self.pan_offset = QPointF(0, 0)
        self.updatePixmap()
        self.setCursor(Qt.ArrowCursor)

    def calculate_fit_zoom(self):
        if self.original_pixmap:
            label_width = self.width()
            label_height = self.height()
            image_width = self.original_pixmap.width()
            image_height = self.original_pixmap.height()

            if image_width > 0 and image_height > 0 and label_width > 0 and label_height > 0:
                width_ratio = label_width / float(image_width)
                height_ratio = label_height / float(image_height)
                self.fit_zoom_factor = min(width_ratio, height_ratio)
                self.fit_zoom_factor = min(1.0, self.fit_zoom_factor)
            else:
                self.fit_zoom_factor = 1.0


    def initial_fit(self):
        self.reset_zoom_pan()


    def mouseDoubleClickEvent(self, event):
        self.reset_zoom_pan()
        self.updatePixmap()


# ----- Main Application Window -----
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RemoveBG") # Changed app name here
        self.setGeometry(100, 100, 1200, 700)
        self.settings = {
            "alpha_matting": False,
            "foreground_threshold": 240,
            "background_threshold": 10,
            "erode_size": 10
        }
        self.original_image_data = None
        self.current_image_path = None
        self.processed_image_data = None # To store processed image data
        self.init_ui()
        self.apply_style()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        image_layout = QHBoxLayout()
        self.originalLabel = ImageLabel("Drop or Open Original Image", main_window=self, is_original=True) # is_original=True for original label
        self.resultLabel = ImageLabel("Processed image will appear here", main_window=self, is_original=False) # is_original=False for result label

        self.resultLabel.setStyleSheet("""
            ImageLabel {
                border: 2px dashed #aaa;
                border-radius: 10px;
                font-size: 14px;
                color: #555;
                padding: 10px;
            }
        """)
        self.originalLabel.setMinimumSize(400, 400)
        self.resultLabel.setMinimumSize(400, 400)

        image_layout.addWidget(self.originalLabel)
        image_layout.addWidget(self.resultLabel)
        main_layout.addLayout(image_layout)

        button_layout = QHBoxLayout()
        open_button = QPushButton("Open Image")
        open_button.clicked.connect(self.openImage)
        self.process_button = QPushButton("Remove Background") # Get process button instance
        self.process_button.clicked.connect(self.processImage)
        save_button = QPushButton("Save Result")
        save_button.clicked.connect(self.saveImage)
        settings_button = QPushButton("Settings")
        settings_button.clicked.connect(self.openSettings)
        reset_zoom_button_original = QPushButton("Reset (Original)") # Changed button text
        reset_zoom_button_original.clicked.connect(self.originalLabel.reset_zoom_pan)
        reset_zoom_button_result = QPushButton("Reset (Processed)") # Changed button text
        reset_zoom_button_result.clicked.connect(self.resultLabel.reset_zoom_pan)


        button_layout.addWidget(open_button)
        button_layout.addWidget(self.process_button)
        button_layout.addWidget(save_button)
        button_layout.addWidget(settings_button)
        button_layout.addWidget(reset_zoom_button_original)
        button_layout.addWidget(reset_zoom_button_result)
        main_layout.addLayout(button_layout)

        self.createMenus()
        self.highlight_process_button() # Highlight process button after UI is created

    def highlight_process_button(self):
        self.process_button.setStyleSheet("""
            QPushButton {
                background-color: #ff9933; /* Orange color to highlight */
                border: none;
                color: white;
                padding: 8px 16px;
                text-align: center;
                font-size: 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #cc7a29; /* Darker orange on hover */
            }
        """ + self.styleSheet()) # Keep the global styles

    def createMenus(self):
        file_menu = self.menuBar().addMenu("&File")
        open_act = QAction("Open...", self)
        open_act.triggered.connect(self.openImage)
        save_act = QAction("Save...", self)
        save_act.triggered.connect(self.saveImage)
        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(open_act)
        file_menu.addAction(save_act)
        file_menu.addSeparator()
        file_menu.addAction(exit_act)

        settings_menu = self.menuBar().addMenu("&Settings")
        advanced_act = QAction("Advanced Settings...", self)
        advanced_act.triggered.connect(self.openSettings)
        settings_menu.addAction(advanced_act)

        help_menu = self.menuBar().addMenu("&Help")
        about_act = QAction("About", self)
        about_act.triggered.connect(self.showAbout)
        help_menu.addAction(about_act)

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QPushButton {
                background-color: #4CAF50;
                border: none;
                color: white;
                padding: 8px 16px;
                text-align: center;
                font-size: 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QMenuBar {
                background-color: #333;
                color: white;
            }
            QMenuBar::item {
                background-color: #333;
                padding: 4px 10px;
                color: white;
            }
            QMenuBar::item:selected {
                background-color: #555;
                color: white;
            }
            QMenu {
                background-color: #f0f0f0;
                color: black;
            }
            QMenu::item:selected {
                background-color: #ddd;
                color: black;
            }
        """)

    def _load_raw_image_data(self, file_path):
        try:
            with open(file_path, "rb") as f:
                self.original_image_data = f.read()
                self.current_image_path = file_path
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read image data:\n{str(e)}")
            self.original_image_data = None
            self.current_image_path = None

    def openImage(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "", "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            loaded_path = self.originalLabel.loadImage(file_path)
            if loaded_path:
                self._load_raw_image_data(loaded_path)

    def processImage(self):
        if not self.original_image_data:
            QMessageBox.warning(self, "No Image", "Please open an image first.")
            return

        try:
            result_data = remove(
                self.original_image_data,
                alpha_matting=self.settings["alpha_matting"],
                alpha_matting_foreground_threshold=self.settings["foreground_threshold"],
                alpha_matting_background_threshold=self.settings["background_threshold"],
                alpha_matting_erode_size=self.settings["erode_size"]
            )
            self.processed_image_data = result_data # Store processed image data
            pixmap = QPixmap()
            pixmap.loadFromData(result_data)
            self.resultLabel.original_pixmap = pixmap
            self.resultLabel.calculate_fit_zoom()
            self.resultLabel.reset_zoom_pan()
            self.resultLabel.updatePixmap()
        except Exception as e:
            QMessageBox.critical(self, "Processing Error", f"Failed to process image:\n{str(e)}")

    def saveImage(self):
        if self.processed_image_data is None: # Check processed_image_data instead of pixmap
            QMessageBox.warning(self, "No Processed Image", "Please process an image first.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Processed Image", "", "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg)"
        )
        if file_path:
            pixmap_to_save = QPixmap() # Create a new pixmap for saving
            pixmap_to_save.loadFromData(self.processed_image_data) # Load from processed data

            if not pixmap_to_save.save(file_path): # Save the pixmap loaded from data
                QMessageBox.critical(self, "Save Error", "Failed to save image.")

    def openSettings(self):
        dialog = SettingsDialog(self, self.settings)
        if dialog.exec_():
            self.settings = dialog.getSettings()

    def showAbout(self):
        QMessageBox.about(
            self, "About RemoveBG",  # Updated about dialog title
            """
            <b>RemoveBG - Background Remover GUI</b><br><br>

            This application uses advanced AI to remove backgrounds from images quickly and easily.<br><br>

            <b>Features:</b><br>
            - Drag and drop or open images via the menu.<br>
            - Side-by-side display of original and processed images.<br>
            - Zoom and pan functionality for detailed inspection.<br>
            - Advanced settings for fine-tuning background removal.<br>
            - Save processed images in PNG or JPEG format.<br><br>

            <b>Developed by:</b> Rudra Mondal<br>
            <b>YouTube Channel:</b> <a href="https://www.youtube.com/@DecodingHub">Decoding Hub</a><br>
            <b>GitHub:</b> <a href="https://github.com/rudra-mondal/">rudra-mondal</a><br><br>

            This tool is for demonstration and personal use.
            """
        )

# ----- Main Execution -----
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())