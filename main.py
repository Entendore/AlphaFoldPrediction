import sys
import subprocess
import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTextEdit, QLabel, QFileDialog, QComboBox, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWebEngineWidgets import QWebEngineView
import tempfile

class AlphaFoldRunner(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(str)
    
    def __init__(self, sequence, output_dir, model_type, db_dir):
        super().__init__()
        self.sequence = sequence
        self.output_dir = output_dir
        self.model_type = model_type
        self.db_dir = db_dir

    def run(self):
        # Save sequence to FASTA
        fasta_path = os.path.join(self.output_dir, "input.fasta")
        with open(fasta_path, "w") as f:
            f.write(f">query\n{self.sequence}\n")
        self.log_signal.emit("FASTA file saved.")

        # Command to run AlphaFold
        cmd = [
            "python3", "run_alphafold.py",
            "--fasta_paths", fasta_path,
            "--output_dir", self.output_dir,
            "--model_preset", self.model_type.lower(),
            "--data_dir", self.db_dir
        ]
        self.log_signal.emit(f"Running AlphaFold ({self.model_type})...")

        # Run process and capture output
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            self.log_signal.emit(line.strip())
            if "Step" in line:
                # crude progress estimate from output lines
                try:
                    step_info = int(line.split()[1])
                    self.progress_signal.emit(step_info)
                except:
                    pass
        process.wait()
        self.finished_signal.emit(self.output_dir)
        self.log_signal.emit("AlphaFold finished.")

class AlphaFoldApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AlphaFold GUI")
        self.setGeometry(100, 100, 1000, 700)
        main_layout = QVBoxLayout()

        # Protein input
        main_layout.addWidget(QLabel("Enter Protein Sequence:"))
        self.sequence_input = QTextEdit()
        main_layout.addWidget(self.sequence_input)

        # Output directory
        out_layout = QHBoxLayout()
        self.output_button = QPushButton("Select Output Directory")
        self.output_button.clicked.connect(self.select_output)
        out_layout.addWidget(self.output_button)
        self.output_label = QLabel("No directory selected")
        out_layout.addWidget(self.output_label)
        main_layout.addLayout(out_layout)

        # Database directory
        db_layout = QHBoxLayout()
        self.db_button = QPushButton("Select AlphaFold Database Directory")
        self.db_button.clicked.connect(self.select_db)
        db_layout.addWidget(self.db_button)
        self.db_label = QLabel("No database selected")
        db_layout.addWidget(self.db_label)
        main_layout.addLayout(db_layout)

        # Model selection
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Select Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["Monomer", "Multimer"])
        model_layout.addWidget(self.model_combo)
        main_layout.addLayout(model_layout)

        # Run button
        self.run_button = QPushButton("Run AlphaFold")
        self.run_button.clicked.connect(self.run_alphafold)
        main_layout.addWidget(self.run_button)

        # Progress bar
        self.progress = QProgressBar()
        main_layout.addWidget(self.progress)

        # Log box
        main_layout.addWidget(QLabel("Logs:"))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        main_layout.addWidget(self.log_box)

        # 3D Viewer
        main_layout.addWidget(QLabel("3D Structure Preview:"))
        self.viewer = QWebEngineView()
        main_layout.addWidget(self.viewer)

        self.output_dir = ""
        self.db_dir = ""
        self.setLayout(main_layout)

    def select_output(self):
        self.output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        self.output_label.setText(self.output_dir)

    def select_db(self):
        self.db_dir = QFileDialog.getExistingDirectory(self, "Select AlphaFold Database Directory")
        self.db_label.setText(self.db_dir)

    def run_alphafold(self):
        sequence = self.sequence_input.toPlainText().strip()
        if not sequence:
            self.log_box.append("Error: No sequence provided.")
            return
        if not self.output_dir:
            self.log_box.append("Error: Select output directory first.")
            return
        if not self.db_dir:
            self.log_box.append("Error: Select AlphaFold database directory.")
            return

        model_type = self.model_combo.currentText()
        self.runner = AlphaFoldRunner(sequence, self.output_dir, model_type, self.db_dir)
        self.runner.log_signal.connect(self.log_box.append)
        self.runner.progress_signal.connect(self.progress.setValue)
        self.runner.finished_signal.connect(self.load_structure)
        self.runner.start()

    def load_structure(self, output_dir):
        # Find the PDB file (simplified: last .pdb in output)
        pdb_files = [f for f in os.listdir(output_dir) if f.endswith(".pdb")]
        if pdb_files:
            pdb_file = os.path.join(output_dir, pdb_files[-1])
            self.show_3d(pdb_file)
            self.log_box.append(f"Loaded PDB: {pdb_file}")

    def show_3d(self, pdb_path):
        # Embed 3Dmol.js in HTML for PyQt QWebEngineView
        with open(pdb_path, 'r') as f:
            pdb_data = f.read()
        html_content = f"""
        <html>
          <head>
            <script src="https://3dmol.csb.pitt.edu/build/3Dmol-min.js"></script>
          </head>
          <body>
            <div id="viewer" style="width:100%; height:500px; position:relative;"></div>
            <script>
              let viewer = $3Dmol.createViewer('viewer', {{backgroundColor:'white'}});
              viewer.addModel(`{pdb_data}`, "pdb");
              viewer.setStyle({{cartoon: {{color:'spectrum'}}}});
              viewer.zoomTo();
              viewer.render();
            </script>
          </body>
        </html>
        """
        tmp_file = os.path.join(tempfile.gettempdir(), "alphafold_viewer.html")
        with open(tmp_file, 'w') as f:
            f.write(html_content)
        self.viewer.load(f"file:///{tmp_file}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AlphaFoldApp()
    window.show()
    sys.exit(app.exec())
