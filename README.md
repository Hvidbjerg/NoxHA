# NoxHA

NoxHA er en custom integration til Home Assistant, som forbinder til en NOX alarm over TCP (typisk Telnet) og opretter entiteter automatisk ud fra de beskeder, der kommer fra centralen.

Integration domain: `noxha`

## Hvad komponentet kan

- Opretter dynamisk `binary_sensor` entiteter for NOX inputs (INP).
- Opretter dynamisk `binary_sensor` entiteter for NOX outputs (OUT).
- Opretter dynamisk `sensor` entiteter for NOX omraader (AREA).
- Holder en persistent TCP-forbindelse med automatisk reconnect ved fejl.
- Opdaterer entitetstilstande i naesten realtid via dispatcher-signaler i Home Assistant.

## Understoettede NOX beskedtyper

NoxHA parser linjebaserede beskeder i dette format:

- INP#I|@I|$I|%I => `INP4|3002-2|DET Stue|closed`
- `OUT1|Gaardlys|off`
- `AREA1|Stueetage|Tilkoblet|0`

Fortolkning:

- `INP...` bliver til en input binary sensor.
- `OUT...` bliver til en output binary sensor.
- `AREA...` bliver til en area sensor med ekstra attributter for alarmstatus.

## NOX Opsætning

Der skal bruges en TIO modul i NOX, som skal sættes op med de korrekte parameter for at dette script kan tyde signaler korrekt.

1. Opsæt din TIO.
2. vælg NOX is Telnet Server
3. vælg dit netværk interface
4. vælg "with delimeter"
5. vælg send all states every 5 minutes
6. setup tekst format for status
   - vælg send inputs opsæt den til at sende INP#I|@I|$I|%I[CR][LF]
   - vælg send outputs opsæt den til at sende OUT#O|$O|%O[CR][LF] vælge on+off
   - vælg send area states opsæt den til at sende AREA#A|$A|%A|$T[CR][LF]

ref:

- #A - Area number
- $A - Area Name
- %A - Area state name
- $T - Alarm Type
- #O - Output number
- $O - Output Name
- %O - Output state name
- #I - Input number (unik)
- @I - ID number (modul+input nummer)
- $I - Input name
- %I Input state name

## Installation

## Via HACS (anbefalet)

1. Åbn HACS i Home Assistant.
2. Vælg Integrations.
3. Tilfoej dit repository som custom repository (type: Integration), hvis det ikke allerede er tilfoejet.
4. Installer NoxHA.
5. Genstart Home Assistant.

## Manuel installation

1. Kopier mappen `custom_components/noxha` til din Home Assistant `custom_components` mappe.
2. Genstart Home Assistant.

## Konfiguration

Konfigureres via UI:

1. Gaa til Settings -> Devices & Services.
2. Klik Add Integration.
3. Soeg efter NoxHA.
4. Indtast:
5. `host`: IP eller hostname paa NOX centralen.
6. `port`: TCP port (default: `23`).

## Entiteter

Integration opretter disse typer:

- Input binary sensors (`binary_sensor`) med auto-device-class baseret paa navn (fx door/window/motion).
- Output binary sensors (`binary_sensor`) for passive output-tilstande.
- Area sensors (`sensor`) med attributter:
- `nox_area_index`
- `alarm_type_code`
- `alarm_status`

Alarm type kode map:

- `0` = Ingen
- `1` = Indbrud
- `2` = Brand
- `3` = Overfald

## Fejlsoegning

Hvis integrationen ikke kan tilfoejes eller du ser `Invalid handler specified`:

1. Kontroller at mappen hedder praecist `custom_components/noxha` (kun smaa bogstaver).
2. Kontroller at `manifest.json` har `"domain": "noxha"` og `"config_flow": true`.
3. Genstart Home Assistant helt.
4. Tjek logs i Home Assistant under Settings -> System -> Logs.

Hvis der ikke oprettes entiteter:

1. Verificer at NOX sender linje-afsluttede beskeder.
2. Verificer host/port.
3. Tjek at firewall tillader forbindelsen.

## Status

Projektet er i tidlig version (`1.0.0`) og kan udbygges med flere NOX felter, validering i config flow og bedre diagnostik.
