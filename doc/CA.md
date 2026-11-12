# Refrigerator

## Entities

### Default entity

No default entity.

### Extra entities

| EntityID                                             | Class         | Description                         |
| ---------------------------------------------------- | ------------- | ----------------------------------- |
| binary_sensor.{DEVICEID}\_bar_door                   | binary_sensor | Bar Door                            |
| binary_sensor.{DEVICEID}\_bar_door_overtime          | binary_sensor | Bar Door Overtime                   |
| binary_sensor.{DEVICEID}\_flex_zone_door             | binary_sensor | Flex-zone Door                      |
| binary_sensor.{DEVICEID}\_flex_zone_door_overtime    | binary_sensor | Flex-zone Door Overtime             |
| binary_sensor.{DEVICEID}\_freezer_door               | binary_sensor | Freezer Door                        |
| binary_sensor.{DEVICEID}\_freezer_door_overtime      | binary_sensor | Freezer Door Overtime               |
| binary_sensor.{DEVICEID}\_refrigerator_door          | binary_sensor | Refrigerator Door                   |
| binary_sensor.{DEVICEID}\_refrigerator_door_overtime | binary_sensor | Refrigerator Door Overtime          |
| binary_sensor.{DEVICEID}\_microcrystal_fresh         | binary_sensor | Microcrystal Fresh                  |
| binary_sensor.{DEVICEID}\_electronic_smell           | binary_sensor | Deodorizing sterilizing             |
| sensor.{DEVICEID}\_flex_zone_actual_temp             | sensor        | Flex-zone Actual Temperature        |
| sensor.{DEVICEID}\_flex_zone_setting_temp            | sensor        | Flex-zone Setting Temperature       |
| sensor.{DEVICEID}\_freezer_actual_temp               | sensor        | Freezer Actual Temperature          |
| sensor.{DEVICEID}\_freezer_setting_temp              | sensor        | Freezer Setting Temperature         |
| sensor.{DEVICEID}\_energy_consumption                | sensor        | Energy Consumptio                   |
| sensor.{DEVICEID}\_refrigerator_actual_temp          | sensor        | Refrigerator Actual Temperature     |
| sensor.{DEVICEID}\_refrigerator_setting_temp         | sensor        | Refrigerator setting Temperature    |
| sensor.{DEVICEID}\_right_flex_zone_actual_temp       | sensor        | Right Flex-zone Actual Temperature  |
| sensor.{DEVICEID}\_right_flex_zone_setting_temp      | sensor        | Right Flex-zone Setting Temperature |
| sensor.{DEVICEID}\_humidity                          | sensor        | Humidity                            |
| sensor.{DEVICEID}\_variable_mode                     | sensor        | Variable Mode                       |

### 310A1394 ice and mode flags

Model `310A1394`, subtype `56`, has four default ice status entities:
`iced_mode`, `ice_mouth_power`, `freezing_ice_machine_water_status`, and
`freezing_all_ice_status`. Their raw bits are shown as Boolean flags; the water
and bin flags have not yet been matched to full/empty labels on a physical unit.
An optional `freezing_ice_machine_power` switch controls the ice maker power.

Additional optional binary sensors expose raw status bits for
`storage_iceHome_door_state`, `freezing_motor_deicing_status`,
`freezing_motor_reset_status`, `smart_mode`, `energy_saving_mode`,
`holiday_mode`, and `acme_freezing_mode`. These are restricted to this model and
subtype. Confirm each flag's physical meaning before using it in automations.
The storage door flag does not mean the ice bin is full.

The integration does not currently write refrigerator target temperatures or
modes. The current target temperature sensors remain read-only.

### 310A2111 flex-zone mode

For model `310A2111`, subtype `56`, the `midea-lan` library derives the App preset
for `variable_mode` from the reported flex-zone **setting** temperature: 6°C is
Mother & Infant (`baby`), 2°C is Treasure (`treasure`), and 0°C is Zero Degree
(`zero`). Other temperatures, missing values, and non-numeric values are
reported as unknown. This is a read-only interpretation; it sends no commands.
Other refrigerator models and subtypes retain their existing mode behavior.

Enable Variable Mode under the integration's extra sensor options. The entity
ID remains `sensor.{DEVICEID}_variable_mode`.

Home Assistant only displays the library's mode keys through translations.
The pinned `midea-lan==2026.10.0` release contains the 310A2111 mapping, and all
locales shipped by the integration provide labels for every variable-mode key.

## Service

The optional ice maker power switch uses the device's latest complete status
frame to preserve unrelated control fields. It rejects a write when that
status is older than two minutes. No other refrigerator control is exposed.
