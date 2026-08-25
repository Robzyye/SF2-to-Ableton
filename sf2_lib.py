"""
sf2_lib.py - Convertisseur SoundFont (.sf2) vers presets Ableton Sampler (.adv)

Ce module ne dépend d'aucune bibliothèque externe (uniquement la stdlib Python).
Il produit exactement la même structure de sortie que l'extension Ableton
"SoundFont Importer" (norakorra/soundfont-importer, licence MIT), mais en
totale autonomie : pas besoin d'Ableton Live 12 bêta ni du SDK d'extensions.

Le format .adv généré est un XML gzippé au schéma "Ableton Live 10.1.43"
(MultiSampler / Sampler standard), lisible nativement par Ableton Live 10,
11 et 12 (toutes éditions Standard/Suite intégrant le Sampler).

Principe de fonctionnement (identique à l'import natif SF2 qu'Ableton
proposait avant la version 11) :
  1. On lit le fichier .sf2 (format RIFF) et on reconstruit la hiérarchie
     preset -> instrument -> zone -> sample avec les generators SF2
     (key range, velocity range, root key, boucle, etc.)
  2. On extrait chaque échantillon audio en fichier .aif (AIFF 16 bits mono).
  3. Pour chaque preset SF2, on génère un fichier .adv (Sampler multi-échantillon)
     qui référence les .aif via un chemin RELATIF à la racine de la
     "User Library" d'Ableton -> Live retrouve donc les samples automatiquement,
     comme n'importe quel autre preset de la bibliothèque utilisateur.

Attribution: logique de parsing/génération portée et adaptée à partir du
projet MIT "soundfont-importer" de Nora Korra (Aaron Werinussa), 2026.
"""

from __future__ import annotations

import gzip
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# --- Generator IDs SF2 utilisés -------------------------------------------------
GEN_INSTRUMENT = 41
GEN_KEY_RANGE = 43
GEN_VEL_RANGE = 44
GEN_COARSE_TUNE = 51
GEN_FINE_TUNE = 52
GEN_SAMPLE_ID = 53
GEN_SAMPLE_MODES = 54
GEN_OVERRIDING_ROOT_KEY = 58

ROM_SAMPLE_FLAG = 0x8000


class Sf2Error(ValueError):
    """Erreur de lecture/format du fichier SoundFont."""


# =============================================================================
# Lecture du conteneur RIFF
# =============================================================================

def _read_chunks(data: bytes, start: int, end: int) -> list[tuple[str, Optional[str], bytes]]:
    chunks = []
    offset = start
    while offset + 8 <= end:
        chunk_id = data[offset : offset + 4].decode("ascii", errors="replace")
        size = struct.unpack_from("<I", data, offset + 4)[0]
        payload_start = offset + 8
        payload_end = payload_start + size
        chunk_type = None
        if chunk_id == "LIST":
            chunk_type = data[payload_start : payload_start + 4].decode("ascii", errors="replace")
            payload_start += 4
        chunks.append((chunk_id, chunk_type, data[payload_start:payload_end]))
        offset = payload_end + (size % 2)  # padding sur 2 octets
    return chunks


def _sf_name(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("latin-1", errors="replace").strip()


# =============================================================================
# Modèle de données
# =============================================================================

@dataclass
class Sf2Sample:
    name: str
    start: int
    end: int
    loop_start: int
    loop_end: int
    sample_rate: int
    original_pitch: int
    pitch_correction: int
    link: int
    type: int


@dataclass
class Sf2Zone:
    sample_index: int
    key_min: int
    key_max: int
    velocity_min: int
    velocity_max: int
    root_key: int
    loop_enabled: bool


@dataclass
class Sf2Preset:
    name: str
    bank: int
    program: int
    zones: list[Sf2Zone] = field(default_factory=list)


@dataclass
class SoundFont:
    name: str
    sample_data: bytes  # PCM 16 bits little-endian, mono, tel que stocké dans le .sf2
    samples: list[Sf2Sample]
    presets: list[Sf2Preset]

    @classmethod
    def from_bytes(cls, data: bytes, source_name: str = "SoundFont") -> "SoundFont":
        if data[0:4] != b"RIFF" or data[8:12] != b"sfbk":
            raise Sf2Error("Ce fichier n'est pas un SoundFont .sf2 valide (en-tête RIFF/sfbk manquant).")

        riff_size = struct.unpack_from("<I", data, 4)[0]
        chunks = _read_chunks(data, 12, 8 + riff_size)

        info: dict[str, str] = {}
        sample_data = b""
        pdta: dict[str, bytes] = {}

        for chunk_id, chunk_type, payload in chunks:
            if chunk_id != "LIST":
                continue
            if chunk_type == "INFO":
                for sub_id, _t, sub_payload in _read_chunks(payload, 0, len(payload)):
                    info[sub_id] = sub_payload.rstrip(b"\x00").decode("latin-1", errors="replace")
            elif chunk_type == "sdta":
                for sub_id, _t, sub_payload in _read_chunks(payload, 0, len(payload)):
                    if sub_id == "smpl":
                        sample_data = sub_payload
                if not sample_data:
                    raise Sf2Error("Le SoundFont ne contient pas de données audio (chunk 'smpl' manquant).")
            elif chunk_type == "pdta":
                for sub_id, _t, sub_payload in _read_chunks(payload, 0, len(payload)):
                    pdta[sub_id] = sub_payload

        required = ("phdr", "pbag", "pgen", "inst", "ibag", "igen", "shdr")
        missing = [name for name in required if name not in pdta]
        if missing:
            raise Sf2Error(f"SoundFont incomplet, chunks manquants: {', '.join(missing)}")

        samples = _parse_samples(pdta["shdr"])
        presets = _build_presets(pdta, samples)
        return cls(
            name=info.get("INAM", "").strip() or source_name,
            sample_data=sample_data,
            samples=samples,
            presets=presets,
        )

    @classmethod
    def from_file(cls, path: Path) -> "SoundFont":
        path = Path(path)
        return cls.from_bytes(path.read_bytes(), source_name=path.stem)


def _parse_samples(data: bytes) -> list[Sf2Sample]:
    records = []
    for offset in range(0, len(data), 46):
        if offset + 46 > len(data):
            break
        name = _sf_name(data[offset : offset + 20])
        start, end, loop_start, loop_end, rate = struct.unpack_from("<IIIII", data, offset + 20)
        original_pitch = data[offset + 40]
        pitch_correction = struct.unpack_from("<b", data, offset + 41)[0]
        link, sample_type = struct.unpack_from("<HH", data, offset + 42)
        records.append(
            Sf2Sample(
                name=name,
                start=start,
                end=end,
                loop_start=loop_start,
                loop_end=loop_end,
                sample_rate=rate or 44100,
                original_pitch=original_pitch,
                pitch_correction=pitch_correction,
                link=link,
                type=sample_type,
            )
        )
    # Le dernier enregistrement shdr est toujours un terminateur "EOS"
    if records and records[-1].name == "EOS":
        records.pop()
    return records


def _range_from_amount(amount: Optional[int]) -> tuple[int, int]:
    if amount is None:
        return 0, 127
    return amount & 0xFF, (amount >> 8) & 0xFF


def _intersect(*ranges: tuple[int, int]) -> tuple[int, int]:
    low = max(0, *(r[0] for r in ranges))
    high = min(127, *(r[1] for r in ranges))
    return low, max(low, high)


def _records(data: bytes, size: int, parser):
    return [parser(data[offset : offset + size]) for offset in range(0, len(data) - size + 1, size)]


def _build_presets(pdta: dict[str, bytes], samples: list[Sf2Sample]) -> list[Sf2Preset]:
    phdr = _records(pdta["phdr"], 38, lambda d: {
        "name": _sf_name(d[:20]),
        "program": struct.unpack_from("<H", d, 20)[0],
        "bank": struct.unpack_from("<H", d, 22)[0],
        "bag_index": struct.unpack_from("<H", d, 24)[0],
    })
    pbag = _records(pdta["pbag"], 4, lambda d: {"gen_index": struct.unpack_from("<H", d, 0)[0]})
    pgen = _records(pdta["pgen"], 4, lambda d: {"op": struct.unpack_from("<H", d, 0)[0], "amount": struct.unpack_from("<H", d, 2)[0]})
    inst = _records(pdta["inst"], 22, lambda d: {"name": _sf_name(d[:20]), "bag_index": struct.unpack_from("<H", d, 20)[0]})
    ibag = _records(pdta["ibag"], 4, lambda d: {"gen_index": struct.unpack_from("<H", d, 0)[0]})
    igen = _records(pdta["igen"], 4, lambda d: {"op": struct.unpack_from("<H", d, 0)[0], "amount": struct.unpack_from("<H", d, 2)[0]})

    def zones_from_bags(bags, gens, start_bag, end_bag):
        zones = []
        for bag_index in range(start_bag, end_bag):
            next_gen = bags[bag_index + 1]["gen_index"] if bag_index + 1 < len(bags) else len(gens)
            gen_items = gens[bags[bag_index]["gen_index"] : next_gen]
            zones.append({item["op"]: item["amount"] for item in gen_items})
        return zones

    # -- instruments --
    instruments = []
    for idx in range(max(0, len(inst) - 1)):
        raw_zones = zones_from_bags(ibag, igen, inst[idx]["bag_index"], inst[idx + 1]["bag_index"])
        global_gens = raw_zones[0] if raw_zones and GEN_SAMPLE_ID not in raw_zones[0] else {}
        zones = [{**global_gens, **z} for z in raw_zones if GEN_SAMPLE_ID in z]
        instruments.append({"name": inst[idx]["name"], "zones": zones})

    # -- presets --
    presets = []
    for idx in range(max(0, len(phdr) - 1)):
        raw_preset_zones = zones_from_bags(pbag, pgen, phdr[idx]["bag_index"], phdr[idx + 1]["bag_index"])
        preset_global = raw_preset_zones[0] if raw_preset_zones and GEN_INSTRUMENT not in raw_preset_zones[0] else {}
        preset_zones = [{**preset_global, **z} for z in raw_preset_zones if GEN_INSTRUMENT in z]

        zones: list[Sf2Zone] = []
        for pz in preset_zones:
            instrument_id = pz.get(GEN_INSTRUMENT)
            if instrument_id is None or instrument_id >= len(instruments):
                continue
            for iz in instruments[instrument_id]["zones"]:
                sample_index = iz.get(GEN_SAMPLE_ID)
                if sample_index is None or sample_index >= len(samples):
                    continue
                key_min, key_max = _intersect(_range_from_amount(pz.get(GEN_KEY_RANGE)), _range_from_amount(iz.get(GEN_KEY_RANGE)))
                vel_min, vel_max = _intersect(_range_from_amount(pz.get(GEN_VEL_RANGE)), _range_from_amount(iz.get(GEN_VEL_RANGE)))
                root = iz.get(GEN_OVERRIDING_ROOT_KEY)
                if root is None or root == 255:
                    root = samples[sample_index].original_pitch or 60
                loop_enabled = bool(iz.get(GEN_SAMPLE_MODES, 0) & 1)
                zones.append(
                    Sf2Zone(
                        sample_index=sample_index,
                        key_min=key_min,
                        key_max=key_max,
                        velocity_min=vel_min,
                        velocity_max=vel_max,
                        root_key=root,
                        loop_enabled=loop_enabled,
                    )
                )
        presets.append(Sf2Preset(name=phdr[idx]["name"], bank=phdr[idx]["bank"], program=phdr[idx]["program"], zones=zones))
    return presets


# =============================================================================
# Export des échantillons en AIFF
# =============================================================================

def _safe_name(value: str, fallback: str = "sample", max_len: int = 72) -> str:
    value = value or fallback
    safe = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in value.strip())
    safe = safe.strip("_") or fallback
    return safe[:max_len]


def _unique_filename(used: set[str], desired: str) -> str:
    stem, dot, ext = desired.rpartition(".")
    ext = "." + ext if dot else ""
    stem = stem if dot else desired
    candidate = desired
    counter = 1
    while candidate.lower() in used:
        candidate = f"{stem}-{counter}{ext}"
        counter += 1
    used.add(candidate.lower())
    return candidate


def _write_extended80(value: float) -> bytes:
    """Encode un flottant en 80 bits étendus IEEE 754 (format requis par AIFF)."""
    buf = bytearray(10)
    if not value:
        return bytes(buf)
    sign = 0x8000 if value < 0 else 0
    number = abs(value)
    import math

    exponent = math.floor(math.log2(number))
    fraction = number / (2**exponent)
    biased = exponent + 16383
    mantissa = int(fraction * (2**63))
    struct.pack_into(">H", buf, 0, sign | biased)
    for i in range(7, -1, -1):
        buf[2 + i] = mantissa & 0xFF
        mantissa >>= 8
    return bytes(buf)


def _aiff_bytes(pcm_le: bytes, frame_count: int, sample_rate: int) -> bytes:
    """Convertit du PCM 16 bits mono little-endian en fichier AIFF (big-endian)."""
    pcm_be = bytearray(len(pcm_le))
    pcm_be[0::2], pcm_be[1::2] = pcm_le[1::2], pcm_le[0::2]

    comm = b"COMM" + struct.pack(">IHIH", 18, 1, frame_count, 16) + _write_extended80(sample_rate or 44100)
    ssnd = b"SSND" + struct.pack(">I", 8 + len(pcm_be)) + struct.pack(">II", 0, 0) + bytes(pcm_be)
    form_payload = b"AIFF" + comm + ssnd
    return b"FORM" + struct.pack(">I", len(form_payload)) + form_payload


@dataclass
class ExportedSample:
    index: int
    name: str
    file_name: str
    path: Path
    file_size: int
    sample_rate: int
    frame_count: int
    original_pitch: int
    loop_start_frames: int
    loop_end_frames: int


def write_aiff_samples(sf2: SoundFont, samples_dir: Path) -> dict[int, ExportedSample]:
    samples_dir.mkdir(parents=True, exist_ok=True)
    exported: dict[int, ExportedSample] = {}
    used_names: set[str] = set()

    for index, sample in enumerate(sf2.samples):
        if sample.end <= sample.start:
            continue
        if sample.type & ROM_SAMPLE_FLAG:
            continue  # échantillon ROM (pas de données audio embarquées)

        pcm = sf2.sample_data[sample.start * 2 : sample.end * 2]
        frame_count = len(pcm) // 2
        if frame_count <= 0:
            continue

        file_name = _unique_filename(used_names, f"{_safe_name(sample.name or f'Sample {index}')}.aif")
        out_path = samples_dir / file_name
        aiff_data = _aiff_bytes(pcm, frame_count, sample.sample_rate)
        out_path.write_bytes(aiff_data)

        exported[index] = ExportedSample(
            index=index,
            name=sample.name or f"Sample {index}",
            file_name=file_name,
            path=out_path,
            file_size=len(aiff_data),
            sample_rate=sample.sample_rate,
            frame_count=frame_count,
            original_pitch=sample.original_pitch,
            loop_start_frames=max(0, sample.loop_start - sample.start),
            loop_end_frames=max(0, sample.loop_end - sample.start),
        )
    return exported


# =============================================================================
# Génération des presets Ableton Sampler (.adv)
# =============================================================================

def _xml_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _relative_path_elements(parts: list[str]) -> str:
    return "".join(f'<RelativePathElement Id="{i}" Dir="{_xml_escape(p)}" />' for i, p in enumerate(parts))


def _multisample_part_xml(zone_id: int, zone: Sf2Zone, sample: ExportedSample, relative_parts: list[str], absolute_parts: list[str]) -> str:
    loop_start = sample.loop_start_frames or 0
    loop_end = max(loop_start, sample.loop_end_frames or sample.frame_count)
    loop_mode = 1 if (zone.loop_enabled and loop_end > loop_start) else 0
    vel_min = max(1, zone.velocity_min)

    return f"""\t\t\t\t\t<MultiSamplePart Id="{zone_id}" HasImportedSlicePoints="false" NeedsAnalysisData="false">
\t\t\t\t\t\t<LomId Value="0" />
\t\t\t\t\t\t<Name Value="{_xml_escape(sample.name)}" />
\t\t\t\t\t\t<Selection Value="{"true" if zone_id == 0 else "false"}" />
\t\t\t\t\t\t<IsActive Value="true" />
\t\t\t\t\t\t<Solo Value="false" />
\t\t\t\t\t\t<KeyRange><Min Value="{zone.key_min}" /><Max Value="{zone.key_max}" /><CrossfadeMin Value="{zone.key_min}" /><CrossfadeMax Value="{zone.key_max}" /></KeyRange>
\t\t\t\t\t\t<VelocityRange><Min Value="{vel_min}" /><Max Value="{zone.velocity_max}" /><CrossfadeMin Value="{vel_min}" /><CrossfadeMax Value="{zone.velocity_max}" /></VelocityRange>
\t\t\t\t\t\t<SelectorRange><Min Value="0" /><Max Value="127" /><CrossfadeMin Value="0" /><CrossfadeMax Value="127" /></SelectorRange>
\t\t\t\t\t\t<RootKey Value="{zone.root_key}" />
\t\t\t\t\t\t<Detune Value="0" />
\t\t\t\t\t\t<TuneScale Value="100" />
\t\t\t\t\t\t<Panorama Value="0" />
\t\t\t\t\t\t<Volume Value="1" />
\t\t\t\t\t\t<Link Value="false" />
\t\t\t\t\t\t<SampleStart Value="0" />
\t\t\t\t\t\t<SampleEnd Value="{max(0, sample.frame_count - 1)}" />
\t\t\t\t\t\t<SustainLoop><Start Value="{loop_start}" /><End Value="{max(0, loop_end - 1)}" /><Mode Value="{loop_mode}" /><Crossfade Value="0" /><Detune Value="0" /></SustainLoop>
\t\t\t\t\t\t<ReleaseLoop><Start Value="0" /><End Value="{max(0, sample.frame_count - 1)}" /><Mode Value="3" /><Crossfade Value="0" /><Detune Value="0" /></ReleaseLoop>
\t\t\t\t\t\t<SampleRef>
\t\t\t\t\t\t\t<FileRef>
\t\t\t\t\t\t\t\t<HasRelativePath Value="true" />
\t\t\t\t\t\t\t\t<RelativePathType Value="6" />
\t\t\t\t\t\t\t\t<RelativePath>{_relative_path_elements(relative_parts)}</RelativePath>
\t\t\t\t\t\t\t\t<Name Value="{_xml_escape(sample.file_name)}" />
\t\t\t\t\t\t\t\t<Type Value="2" />
\t\t\t\t\t\t\t\t<Data />
\t\t\t\t\t\t\t\t<RefersToFolder Value="false" />
\t\t\t\t\t\t\t\t<SearchHint><PathHint>{_relative_path_elements(absolute_parts)}</PathHint><FileSize Value="{sample.file_size}" /><Crc Value="0" /></SearchHint>
\t\t\t\t\t\t\t\t<LivePackName Value="" />
\t\t\t\t\t\t\t\t<LivePackId Value="" />
\t\t\t\t\t\t\t</FileRef>
\t\t\t\t\t\t\t<LastModDate Value="{int(time.time())}" />
\t\t\t\t\t\t\t<SourceContext />
\t\t\t\t\t\t\t<SampleUsageHint Value="0" />
\t\t\t\t\t\t\t<DefaultDuration Value="{sample.frame_count}" />
\t\t\t\t\t\t\t<DefaultSampleRate Value="{sample.sample_rate}" />
\t\t\t\t\t\t</SampleRef>
\t\t\t\t\t\t<SlicingThreshold Value="100" />
\t\t\t\t\t\t<SlicingBeatGrid Value="4" />
\t\t\t\t\t\t<SlicingRegionCount Value="8" />
\t\t\t\t\t\t<SlicingStyle Value="0" />
\t\t\t\t\t\t<SlicingSensitivity Value="1" />
\t\t\t\t\t\t<BeatSlices><BeatSlice Id="0" TimeInSeconds="0" Rank="0" NormalizedEnergy="0" /><BeatSlice Id="1" TimeInSeconds="0" Rank="0" NormalizedEnergy="0" /></BeatSlices>
\t\t\t\t\t\t<UseDynamicBeatSlices Value="true" />
\t\t\t\t\t\t<UseDynamicRegionSlices Value="true" />
\t\t\t\t\t</MultiSamplePart>"""


def _sampler_preset_xml(preset_name: str, zones: list[Sf2Zone], exported_by_index: dict[int, ExportedSample], relative_parts: list[str], absolute_parts: list[str]) -> str:
    parts_xml = "\n".join(
        _multisample_part_xml(i, zone, exported_by_index[zone.sample_index], relative_parts, absolute_parts)
        for i, zone in enumerate(zones)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Ableton MajorVersion="5" MinorVersion="10.0_377" SchemaChangeCount="6" Creator="Ableton Live 10.1.43" Revision="0e617fc8048569557b05b35c5dcc68f74fed435a">
\t<MultiSampler>
\t\t<LomId Value="0" />
\t\t<LomIdView Value="0" />
\t\t<IsExpanded Value="true" />
\t\t<On>
\t\t\t<LomId Value="0" />
\t\t\t<Manual Value="true" />
\t\t\t<AutomationTarget Id="0"><LockEnvelope Value="0" /></AutomationTarget>
\t\t\t<MidiCCOnOffThresholds><Min Value="64" /><Max Value="127" /></MidiCCOnOffThresholds>
\t\t</On>
\t\t<ParametersListWrapper LomId="0" />
\t\t<LastSelectedTimeableIndex Value="0" />
\t\t<LastSelectedClipEnvelopeIndex Value="0" />
\t\t<LastPresetRef><Value /></LastPresetRef>
\t\t<LockedScripts />
\t\t<IsFolded Value="false" />
\t\t<ShouldShowPresetName Value="true" />
\t\t<UserName Value="{_xml_escape(preset_name)}" />
\t\t<Annotation Value="" />
\t\t<SourceContext><Value /></SourceContext>
\t\t<OverwriteProtectionNumber Value="1000" />
\t\t<Player>
\t\t\t<MultiSampleMap>
\t\t\t\t<SampleParts>
{parts_xml}
\t\t\t\t</SampleParts>
\t\t\t\t<LoadInRam Value="false" />
\t\t\t\t<LayerCrossfade Value="0" />
\t\t\t\t<SourceContext />
\t\t\t</MultiSampleMap>
\t\t\t<Reverse><LomId Value="0" /><Manual Value="false" /><AutomationTarget Id="0"><LockEnvelope Value="0" /></AutomationTarget><MidiCCOnOffThresholds><Min Value="64" /><Max Value="127" /></MidiCCOnOffThresholds></Reverse>
\t\t\t<Snap><LomId Value="0" /><Manual Value="false" /><AutomationTarget Id="0"><LockEnvelope Value="0" /></AutomationTarget><MidiCCOnOffThresholds><Min Value="64" /><Max Value="127" /></MidiCCOnOffThresholds></Snap>
\t\t\t<InterpolationMode Value="1" />
\t\t\t<UseConstPowCrossfade Value="true" />
\t\t</Player>
\t\t<Pitch><TransposeKey><LomId Value="0" /><Manual Value="0" /><MidiControllerRange><Min Value="-48" /><Max Value="48" /></MidiControllerRange><AutomationTarget Id="0"><LockEnvelope Value="0" /></AutomationTarget><ModulationTarget Id="0"><LockEnvelope Value="0" /></ModulationTarget></TransposeKey><TransposeFine><LomId Value="0" /><Manual Value="0" /><MidiControllerRange><Min Value="-50" /><Max Value="50" /></MidiControllerRange><AutomationTarget Id="0"><LockEnvelope Value="0" /></AutomationTarget><ModulationTarget Id="0"><LockEnvelope Value="0" /></ModulationTarget></TransposeFine><ScrollPosition Value="-1073741824" /></Pitch>
\t\t<Filter><IsOn><LomId Value="0" /><Manual Value="false" /><AutomationTarget Id="0"><LockEnvelope Value="0" /></AutomationTarget><MidiCCOnOffThresholds><Min Value="64" /><Max Value="127" /></MidiCCOnOffThresholds></IsOn><Slot><Value /></Slot></Filter>
\t\t<Volume><Volume><LomId Value="0" /><Manual Value="1" /><MidiControllerRange><Min Value="0.0003162277571" /><Max Value="1" /></MidiControllerRange><AutomationTarget Id="0"><LockEnvelope Value="0" /></AutomationTarget><ModulationTarget Id="0"><LockEnvelope Value="0" /></ModulationTarget></Volume></Volume>
\t\t<Envelope><AttackTime><LomId Value="0" /><Manual Value="1" /><MidiControllerRange><Min Value="0" /><Max Value="60000" /></MidiControllerRange><AutomationTarget Id="0"><LockEnvelope Value="0" /></AutomationTarget><ModulationTarget Id="0"><LockEnvelope Value="0" /></ModulationTarget></AttackTime><DecayTime><LomId Value="0" /><Manual Value="60000" /><MidiControllerRange><Min Value="1" /><Max Value="60000" /></MidiControllerRange><AutomationTarget Id="0"><LockEnvelope Value="0" /></AutomationTarget><ModulationTarget Id="0"><LockEnvelope Value="0" /></ModulationTarget></DecayTime><SustainLevel><LomId Value="0" /><Manual Value="1" /><MidiControllerRange><Min Value="0.0003162277571" /><Max Value="1" /></MidiControllerRange><AutomationTarget Id="0"><LockEnvelope Value="0" /></AutomationTarget><ModulationTarget Id="0"><LockEnvelope Value="0" /></ModulationTarget></SustainLevel><ReleaseTime><LomId Value="0" /><Manual Value="50" /><MidiControllerRange><Min Value="1" /><Max Value="60000" /></MidiControllerRange><AutomationTarget Id="0"><LockEnvelope Value="0" /></AutomationTarget><ModulationTarget Id="0"><LockEnvelope Value="0" /></ModulationTarget></ReleaseTime></Envelope>
\t\t<VoiceSettings><Voices Value="16" /><VoiceMode Value="0" /><Retrigger Value="true" /></VoiceSettings>
\t</MultiSampler>
</Ableton>
"""


@dataclass
class ConversionResult:
    preset_count: int
    sample_count: int
    zone_count: int
    skipped_presets: list[str]
    samples_dir: Path
    presets_dir: Path


def write_sampler_presets(
    sf2: SoundFont,
    exported: dict[int, ExportedSample],
    presets_dir: Path,
    samples_dir: Path,
    user_library_root: Path,
    preset_filter: Optional[str] = None,
) -> ConversionResult:
    presets_dir.mkdir(parents=True, exist_ok=True)
    relative_parts = list(samples_dir.resolve().relative_to(user_library_root.resolve()).parts)
    absolute_parts = [p for p in samples_dir.resolve().parts if p not in ("/", "\\")]

    used_names: set[str] = set()
    preset_count = 0
    zone_count = 0
    skipped: list[str] = []

    for preset in sf2.presets:
        if preset_filter and preset_filter.lower() not in preset.name.lower():
            continue
        zones = [z for z in preset.zones if z.sample_index in exported]
        if not zones:
            if preset_filter:
                skipped.append(preset.name)
            continue

        file_name = _unique_filename(used_names, f"{_safe_name(preset.name or f'Preset {preset_count + 1}')}.adv")
        xml = _sampler_preset_xml(preset.name or Path(file_name).stem, zones, exported, relative_parts, absolute_parts)
        (presets_dir / file_name).write_bytes(gzip.compress(xml.encode("utf-8"), compresslevel=9))
        preset_count += 1
        zone_count += len(zones)

    return ConversionResult(
        preset_count=preset_count,
        sample_count=len(exported),
        zone_count=zone_count,
        skipped_presets=skipped,
        samples_dir=samples_dir,
        presets_dir=presets_dir,
    )


# =============================================================================
# Orchestration haut niveau
# =============================================================================

def next_available_dir(base: Path) -> Path:
    if not base.exists():
        return base
    for i in range(1, 1000):
        candidate = base.with_name(f"{base.name}-{i}")
        if not candidate.exists():
            return candidate
    return base.with_name(f"{base.name}-{int(time.time())}")


def convert_sf2(
    sf2_path: Path,
    user_library_root: Path,
    preset_filter: Optional[str] = None,
) -> ConversionResult:
    """Point d'entrée principal : convertit un fichier .sf2 en presets Ableton Sampler.

    Produit, sous `user_library_root` (la racine de la "User Library" d'Ableton) :
      Samples/<nom_du_soundfont>/*.aif
      SoundFont Imports/<nom_du_soundfont>/*.adv
    """
    sf2_path = Path(sf2_path).expanduser().resolve()
    user_library_root = Path(user_library_root).expanduser().resolve()
    user_library_root.mkdir(parents=True, exist_ok=True)

    sf2 = SoundFont.from_file(sf2_path)
    base_name = _safe_name(sf2.name or sf2_path.stem)

    samples_dir = next_available_dir(user_library_root / "Samples" / base_name)
    presets_dir = next_available_dir(user_library_root / "SoundFont Imports" / base_name)

    exported = write_aiff_samples(sf2, samples_dir)
    if not exported:
        raise Sf2Error("Aucun échantillon audio exploitable n'a été trouvé dans ce SoundFont.")

    result = write_sampler_presets(sf2, exported, presets_dir, samples_dir, user_library_root, preset_filter)
    if result.preset_count == 0:
        raise Sf2Error(
            "Aucun preset n'a pu être généré"
            + (f" pour le filtre « {preset_filter} »." if preset_filter else " (SoundFont vide ou incompatible.)")
        )
    return result


def find_sf2_files(folder: Path) -> list[Path]:
    """Cherche récursivement tous les fichiers .sf2 sous `folder` (insensible à la casse)."""
    folder = Path(folder)
    seen: dict[str, Path] = {}
    for candidate in folder.rglob("*"):
        if candidate.is_file() and candidate.suffix.lower() == ".sf2":
            seen[str(candidate.resolve()).lower()] = candidate
    return sorted(seen.values(), key=lambda p: str(p).lower())


@dataclass
class BatchItem:
    sf2_path: Path
    result: Optional[ConversionResult] = None
    error: Optional[str] = None


def batch_convert(
    sf2_paths: list[Path],
    user_library_root: Path,
    preset_filter: Optional[str] = None,
    on_progress=None,
) -> list[BatchItem]:
    """Convertit une liste de fichiers .sf2, en continuant même si l'un d'eux échoue.

    `on_progress(index, total, item)` est appelé après chaque fichier traité
    (item.error est renseigné en cas d'échec, item.result sinon).
    """
    items: list[BatchItem] = []
    total = len(sf2_paths)
    for index, sf2_path in enumerate(sf2_paths, start=1):
        item = BatchItem(sf2_path=sf2_path)
        try:
            item.result = convert_sf2(sf2_path, user_library_root, preset_filter)
        except Exception as exc:  # on isole chaque fichier : un échec ne doit jamais stopper le lot
            item.error = str(exc)
        items.append(item)
        if on_progress:
            on_progress(index, total, item)
    return items
