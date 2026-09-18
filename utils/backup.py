"""
utils/backup.py

Gerenciamento de cópias de segurança (backup) do banco de dados.

CONCEITO:
Backup aqui é copiar o ARQUIVO JÁ CIFRADO (.db.enc) para uma pasta
separada, com um carimbo de data/hora no nome. Como o arquivo já está
criptografado (ver database/connection.py), o backup herda a mesma
proteção sem precisar cifrar de novo — é só uma cópia de um arquivo
que já é ilegível sem a senha.

POR QUE UMA PASTA SEPARADA:
Se o arquivo principal corromper (queda de energia no meio de uma
gravação, disco com setor ruim, etc.), a cópia mais recente na pasta
de backup continua íntegra. Backup na mesma pasta do original não
protege contra nada — os dois morrem juntos.

POLÍTICA DE RETENÇÃO:
Sem limite, backups acumulam disco pra sempre. Mantemos só as N cópias
mais recentes (padrão: 10) — as mais antigas são apagadas automaticamente
a cada novo backup criado.
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


class BackupManager:
    def __init__(self, source_path: str, backup_dir: str, max_backups: int = 10):
        self.source_path = Path(source_path)
        self.backup_dir = Path(backup_dir)
        self.max_backups = max_backups
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def criar_backup(self) -> Path:
        """
        Copia o arquivo de banco (já criptografado) para a pasta de
        backup, com carimbo de data/hora no nome.
        Retorna o caminho do arquivo de backup criado.
        """
        if not self.source_path.exists():
            raise FileNotFoundError(
                f"Banco de dados não encontrado em '{self.source_path}' — nada para copiar."
            )

        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_backup = f"{self.source_path.stem}_{carimbo}{self.source_path.suffix}"
        caminho_backup = self.backup_dir / nome_backup

        shutil.copy2(self.source_path, caminho_backup)
        self._aplicar_retencao()
        return caminho_backup

    def _aplicar_retencao(self) -> None:
        """Mantém só os N backups mais recentes; apaga os excedentes mais antigos."""
        for antigo in self.listar_backups()[self.max_backups:]:
            antigo.unlink()

    def listar_backups(self) -> list[Path]:
        """Lista os backups existentes, do mais recente para o mais antigo."""
        padrao = f"{self.source_path.stem}_*{self.source_path.suffix}"
        return sorted(
            self.backup_dir.glob(padrao),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    def restaurar_backup(self, caminho_backup: Path, destino: Optional[str] = None) -> Path:
        """
        Restaura um backup específico, sobrescrevendo o banco atual
        (ou copiando para outro destino, se 'destino' for informado —
        útil pra testar a restauração sem mexer no banco de verdade).
        """
        destino_final = Path(destino) if destino else self.source_path
        shutil.copy2(caminho_backup, destino_final)
        return destino_final
