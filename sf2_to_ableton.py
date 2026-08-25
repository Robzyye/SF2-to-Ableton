#!/usr/bin/env python3
r"""
SF2 -> Ableton Sampler — convertisseur autonome (sans extension Live 12 bêta)

Utilisation en ligne de commande :
    python3 sf2_to_ableton.py mon_fichier.sf2
    python3 sf2_to_ableton.py mon_fichier.sf2 --user-library "/chemin/vers/User Library"
    python3 sf2_to_ableton.py mon_fichier.sf2 --filter "Piano"
    python3 sf2_to_ableton.py --list mon_fichier.sf2        # liste les presets sans convertir

    # Dossier entier (recherche récursive de tous les .sf2, sous-dossiers inclus) :
    python3 sf2_to_ableton.py "C:\Mes SoundFonts"
    python3 sf2_to_ableton.py "C:\Mes SoundFonts" --user-library "D:\Ableton\User Library"

Sans argument, une fenêtre s'ouvre (double-clic sur le fichier).

Ce script ne modifie pas Ableton Live ni ses préférences : il écrit simplement
des fichiers .aif (échantillons) et .adv (presets Sampler) dans la "User
Library" d'Ableton, exactement comme le ferait l'import natif présent dans
les anciennes versions de Live. Fonctionne avec Live 10, 11 et 12 (pas besoin
de la bêta ni du SDK d'extensions).
"""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

from sf2_lib import SoundFont, Sf2Error, convert_sf2, find_sf2_files, batch_convert


def default_user_library() -> Path:
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return home / "Music" / "Ableton" / "User Library"
    if system == "Windows":
        return home / "Documents" / "Ableton" / "User Library"
    # Linux / autre : pas de convention officielle Ableton, on retombe sur un
    # dossier local que l'utilisateur pourra glisser lui-même dans Places.
    return home / "Ableton User Library"


def cmd_list(sf2_path: Path) -> int:
    try:
        sf2 = SoundFont.from_file(sf2_path)
    except Sf2Error as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    print(f"SoundFont : {sf2.name}")
    print(f"{len(sf2.samples)} échantillons, {len(sf2.presets)} presets\n")
    for preset in sf2.presets:
        print(f"  [banque {preset.bank:>3} / prog {preset.program:>3}] {preset.name}  ({len(preset.zones)} zones)")
    return 0


def cmd_convert(sf2_path: Path, user_library: Path, preset_filter: str | None) -> int:
    print(f"Lecture de {sf2_path.name}...")
    try:
        result = convert_sf2(sf2_path, user_library, preset_filter)
    except Sf2Error as exc:
        print(f"\nÉchec de la conversion : {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print(f"\nFichier introuvable : {sf2_path}", file=sys.stderr)
        return 1

    print()
    print(f"✔ {result.preset_count} preset(s) Sampler générés ({result.zone_count} zones, {result.sample_count} échantillons)")
    print(f"  Échantillons : {result.samples_dir}")
    print(f"  Presets      : {result.presets_dir}")
    if result.skipped_presets:
        print(f"  (filtrés/ignorés : {', '.join(result.skipped_presets)})")
    print()
    print('Dans Ableton Live : Browser > Places > clic droit > "Add Folder",')
    print(f'sélectionnez le dossier "SoundFont Imports" dans :\n  {user_library}')
    print("(à faire une seule fois — les prochaines conversions apparaîtront automatiquement dedans)")
    return 0


def cmd_batch(folder: Path, user_library: Path, preset_filter: str | None) -> int:
    sf2_files = find_sf2_files(folder)
    if not sf2_files:
        print(f"Aucun fichier .sf2 trouvé dans {folder} (recherche récursive).", file=sys.stderr)
        return 1

    print(f"{len(sf2_files)} fichier(s) .sf2 trouvé(s) dans {folder}\n")

    def on_progress(index, total, item):
        if item.error:
            print(f"[{index}/{total}] ✘ {item.sf2_path.name} — {item.error}")
        else:
            print(f"[{index}/{total}] ✔ {item.sf2_path.name} — {item.result.preset_count} preset(s)")

    items = batch_convert(sf2_files, user_library, preset_filter, on_progress=on_progress)

    succeeded = [i for i in items if i.result]
    failed = [i for i in items if i.error]
    total_presets = sum(i.result.preset_count for i in succeeded)
    total_samples = sum(i.result.sample_count for i in succeeded)

    print()
    print(f"Terminé : {len(succeeded)}/{len(items)} SoundFont(s) convertis avec succès.")
    print(f"Total : {total_presets} presets, {total_samples} échantillons.")
    if failed:
        print(f"\n{len(failed)} échec(s) :")
        for item in failed:
            print(f"  - {item.sf2_path} : {item.error}")

    if succeeded:
        print()
        print('Dans Ableton Live : Browser > Places > clic droit > "Add Folder",')
        print(f'sélectionnez le dossier "SoundFont Imports" dans :\n  {user_library}')
        print("(à faire une seule fois — chaque SoundFont a son propre sous-dossier de presets)")

    return 0 if not failed else 2


def run_gui() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        print("Tkinter n'est pas disponible sur ce Python. Utilisez la ligne de commande :")
        print("  python3 sf2_to_ableton.py mon_fichier.sf2")
        return 1

    import queue
    import threading

    root = tk.Tk()
    root.title("SF2 → Ableton Sampler")
    root.resizable(False, False)
    padding = {"padx": 12, "pady": 6}

    input_var = tk.StringVar()
    lib_var = tk.StringVar(value=str(default_user_library()))
    filter_var = tk.StringVar()
    status_var = tk.StringVar(value="Choisissez un fichier .sf2, ou un dossier qui en contient plusieurs.")

    frame = ttk.Frame(root)
    frame.grid(row=0, column=0, sticky="nsew", **padding)

    progress = ttk.Progressbar(frame, mode="determinate", length=420)
    log_box = tk.Text(frame, width=64, height=10, state="disabled", wrap="word")

    ui_queue: "queue.Queue" = queue.Queue()
    convert_button: ttk.Button

    def log(line: str):
        log_box.configure(state="normal")
        log_box.insert("end", line + "\n")
        log_box.see("end")
        log_box.configure(state="disabled")

    def pick_sf2_file():
        path = filedialog.askopenfilename(title="Choisir un SoundFont", filetypes=[("SoundFont", "*.sf2"), ("Tous les fichiers", "*.*")])
        if path:
            input_var.set(path)
            status_var.set("Prêt à convertir ce fichier.")

    def pick_sf2_folder():
        path = filedialog.askdirectory(title="Choisir un dossier contenant des .sf2 (sous-dossiers inclus)")
        if path:
            input_var.set(path)
            status_var.set("Prêt à convertir tous les .sf2 de ce dossier.")

    def pick_lib():
        path = filedialog.askdirectory(title="Choisir le dossier User Library d'Ableton")
        if path:
            lib_var.set(path)

    def set_running(running: bool):
        state = "disabled" if running else "normal"
        convert_button.configure(state=state)

    def poll_queue():
        try:
            while True:
                kind, payload = ui_queue.get_nowait()
                if kind == "progress":
                    index, total, item = payload
                    progress.configure(maximum=total, value=index)
                    if item.error:
                        log(f"[{index}/{total}] ✘ {item.sf2_path.name} — {item.error}")
                    else:
                        log(f"[{index}/{total}] ✔ {item.sf2_path.name} — {item.result.preset_count} preset(s)")
                elif kind == "status":
                    status_var.set(payload)
                elif kind == "done_single":
                    set_running(False)
                    result, error = payload
                    if error:
                        status_var.set("Échec.")
                        messagebox.showerror("Échec de la conversion", error)
                    else:
                        status_var.set(f"Terminé : {result.preset_count} presets générés.")
                        messagebox.showinfo(
                            "Conversion terminée",
                            f"{result.preset_count} preset(s) générés ({result.sample_count} échantillons, {result.zone_count} zones).\n\n"
                            f"Presets : {result.presets_dir}\n\n"
                            "Dans Ableton : Browser > Places > clic droit > Add Folder,\n"
                            f'puis choisissez le dossier "SoundFont Imports" dans :\n{lib_var.get()}\n\n'
                            "(à faire une seule fois)",
                        )
                elif kind == "done_batch":
                    set_running(False)
                    items = payload
                    succeeded = [i for i in items if i.result]
                    failed = [i for i in items if i.error]
                    total_presets = sum(i.result.preset_count for i in succeeded)
                    status_var.set(f"Terminé : {len(succeeded)}/{len(items)} SoundFonts convertis, {total_presets} presets.")
                    msg = f"{len(succeeded)}/{len(items)} SoundFont(s) convertis avec succès.\nTotal : {total_presets} presets.\n"
                    if failed:
                        msg += f"\n{len(failed)} échec(s) — voir le journal dans la fenêtre."
                    msg += (
                        '\n\nDans Ableton : Browser > Places > clic droit > Add Folder,\n'
                        f'puis choisissez le dossier "SoundFont Imports" dans :\n{lib_var.get()}'
                    )
                    messagebox.showinfo("Conversion en lot terminée", msg)
        except queue.Empty:
            pass
        root.after(100, poll_queue)

    def do_convert():
        input_path_str = input_var.get().strip()
        lib_path_str = lib_var.get().strip()
        if not input_path_str:
            messagebox.showwarning("Rien à convertir", "Choisissez un fichier .sf2 ou un dossier.")
            return
        if not lib_path_str:
            messagebox.showwarning("Dossier manquant", "Indiquez le dossier User Library d'Ableton.")
            return
        input_path = Path(input_path_str)
        if not input_path.exists():
            messagebox.showerror("Introuvable", f"Ce chemin n'existe pas :\n{input_path}")
            return

        user_library = Path(lib_path_str)
        preset_filter = filter_var.get().strip() or None

        log_box.configure(state="normal")
        log_box.delete("1.0", "end")
        log_box.configure(state="disabled")
        progress.configure(value=0)
        set_running(True)

        if input_path.is_dir():
            status_var.set("Recherche des fichiers .sf2...")

            def worker():
                sf2_files = find_sf2_files(input_path)
                if not sf2_files:
                    ui_queue.put(("done_batch", []))
                    ui_queue.put(("status", "Aucun .sf2 trouvé dans ce dossier."))
                    return
                ui_queue.put(("status", f"{len(sf2_files)} fichier(s) trouvé(s), conversion en cours..."))

                def on_progress(index, total, item):
                    ui_queue.put(("progress", (index, total, item)))

                items = batch_convert(sf2_files, user_library, preset_filter, on_progress=on_progress)
                ui_queue.put(("done_batch", items))

            threading.Thread(target=worker, daemon=True).start()
        else:
            status_var.set("Conversion en cours...")

            def worker():
                try:
                    result = convert_sf2(input_path, user_library, preset_filter)
                    ui_queue.put(("done_single", (result, None)))
                except Sf2Error as exc:
                    ui_queue.put(("done_single", (None, str(exc))))
                except Exception as exc:
                    ui_queue.put(("done_single", (None, str(exc))))

            threading.Thread(target=worker, daemon=True).start()

    ttk.Label(frame, text="Fichier .sf2, OU dossier contenant plusieurs .sf2").grid(row=0, column=0, sticky="w")
    ttk.Entry(frame, textvariable=input_var, width=52).grid(row=1, column=0, sticky="we")
    button_row = ttk.Frame(frame)
    button_row.grid(row=1, column=1, padx=(6, 0))
    ttk.Button(button_row, text="Fichier…", command=pick_sf2_file).grid(row=0, column=0)
    ttk.Button(button_row, text="Dossier…", command=pick_sf2_folder).grid(row=0, column=1, padx=(4, 0))

    ttk.Label(frame, text="Dossier « User Library » d'Ableton").grid(row=2, column=0, sticky="w", pady=(10, 0))
    ttk.Entry(frame, textvariable=lib_var, width=52).grid(row=3, column=0, sticky="we")
    ttk.Button(frame, text="Parcourir…", command=pick_lib).grid(row=3, column=1, padx=(6, 0))

    ttk.Label(frame, text="Filtrer les presets (optionnel, ex. « Piano »)").grid(row=4, column=0, sticky="w", pady=(10, 0))
    ttk.Entry(frame, textvariable=filter_var, width=52).grid(row=5, column=0, sticky="we")

    convert_button = ttk.Button(frame, text="Convertir", command=do_convert)
    convert_button.grid(row=6, column=0, columnspan=2, sticky="we", pady=(14, 4))
    ttk.Label(frame, textvariable=status_var, foreground="#555").grid(row=7, column=0, columnspan=2, sticky="w")
    progress.grid(row=8, column=0, columnspan=2, sticky="we", pady=(8, 4))
    log_box.grid(row=9, column=0, columnspan=2, sticky="we")

    root.after(100, poll_queue)
    root.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convertit un ou plusieurs SoundFonts (.sf2) en presets Ableton Sampler (.adv), sans extension Live 12 bêta.")
    parser.add_argument("sf2", nargs="?", help="Fichier .sf2, OU dossier contenant des .sf2 (recherche récursive dans les sous-dossiers)")
    parser.add_argument("--user-library", "-u", default=None, help="Racine de la User Library Ableton (par défaut : détection automatique selon l'OS)")
    parser.add_argument("--filter", "-f", default=None, help="Ne convertir que les presets dont le nom contient ce texte")
    parser.add_argument("--list", "-l", action="store_true", help="Lister les presets du SoundFont sans rien convertir (fichier unique uniquement)")
    args = parser.parse_args(argv)

    if not args.sf2:
        return run_gui()

    input_path = Path(args.sf2)
    if not input_path.exists():
        print(f"Introuvable : {input_path}", file=sys.stderr)
        return 1

    user_library = Path(args.user_library) if args.user_library else default_user_library()

    if input_path.is_dir():
        if args.list:
            print("--list n'est disponible que pour un fichier .sf2 unique, pas pour un dossier.", file=sys.stderr)
            return 1
        return cmd_batch(input_path, user_library, args.filter)

    if args.list:
        return cmd_list(input_path)

    return cmd_convert(input_path, user_library, args.filter)


if __name__ == "__main__":
    raise SystemExit(main())
