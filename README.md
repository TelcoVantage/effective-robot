# Dropped Call Monitor for Genesys Cloud

Logs every voice call that **dropped because of our side** (platform error, system disconnect,
timeout, transport failure) **and carries an error participant attribute**, into a Genesys Cloud
data table you can review and export. No code to run: everything is imported through the
Genesys Cloud admin UI.

```
 customer session ends            TRIGGER                      WORKFLOW                              DATA TABLE
 (any voice call)      ──►  mediaType = VOICE          ──►  1. Get conversation drop details  ──►  Dropped Call Log
                            disconnectType in               (data action: reads ErrorCode /        one row per
                            ERROR, SYSTEM, TIMEOUT,          ErrorMessage attributes, queue,        conversation
                            TRANSPORT_FAILURE                agent, start/end time)
                                                           2. Classify the disconnect type
                                                           3. Skip if there is no error attribute
                                                              (configurable)
                                                           4. Write Dropped Call Log row
                                                              (data action: POST data table row)
```

## What is in this package

| Folder | File | Import where |
|---|---|---|
| `genesys/1-data-actions` | `Get Conversation Drop Details.json` | Admin > Integrations > Actions > **Import** |
| `genesys/1-data-actions` | `Write Dropped Call Log Row.json` | Admin > Integrations > Actions > **Import** |
| `genesys/2-data-table` | `Dropped Call Log - fields.csv` | Field list to create the table (Admin > Architect > Data Tables) |
| `genesys/2-data-table` | `Dropped Call Log - import template.csv` | Optional: Data Tables > Manage Imports (one example row) |
| `genesys/3-workflow` | `Dropped Call Monitor.i3WorkFlow` | Architect > Flows > Workflow > Save menu > **Import** |
| `genesys/3-workflow` | `Dropped Call Monitor.yaml` | Same workflow for Archy (fallback / readable reference) |
| `genesys/4-trigger` | `Dropped Call Monitor - trigger.json` | Values for Admin > Triggers (or paste into API Explorer) |
| `genesys/4-trigger` | `sample-test-event.json` | Paste into the trigger's **Save & Test** window |

Install in this order: **integration & permissions → data table → data actions → workflow → trigger**.
Each step depends on the previous one.

---

## Step 0. Integration and permissions (5 min, usually already in place)

The workflow calls two Genesys Cloud data actions. They run under a **Genesys Cloud Data Actions**
integration, which authenticates with an OAuth client (client credentials).

1. Admin > Integrations > OAuth: the OAuth client used by your Genesys Cloud Data Actions integration
   needs a role that includes these permissions:
   - `Conversation > Communication > View` (read the conversation and its participant attributes)
   - `Architect > Data Table Row > Add` (write log rows)
   - `Architect > Data Table > View`
2. Admin > Integrations > Integrations: make sure a **Genesys Cloud Data Actions** integration exists
   and is **Active**. Note its exact name. The workflow expects the default name
   `Genesys Cloud Data Actions`. If yours is named differently, that is fine: you re-select it once in
   Step 3.

## Step 1. Create the data table (5 min)

1. Admin > Architect > **Data Tables** > **Add**.
2. Name: `Dropped Call Log`. Reference key label: `ConversationId`.
3. Add the custom fields exactly as listed in `genesys/2-data-table/Dropped Call Log - fields.csv`.
   All fields are type **String**. Type the labels with no spaces, exactly as written
   (`CallStartTime`, `CallEndTime`, `DisconnectType`, `DropCategory`, `ErrorCode`, `ErrorMessage`,
   `Direction`, `ANI`, `DNIS`, `QueueName`, `AgentName`, `LookupStatus`, `Reviewed`).
   Give `Reviewed` the default value `No`.
4. Save. Open the table and check that each field's **API Field ID** equals its label. The write
   data action posts rows using these IDs, so they must match.
5. Copy the table **ID** from the browser URL (the GUID after `/datatables/`). You need it in Step 3.
6. Optional: Manage Imports > Select Import File > `Dropped Call Log - import template.csv` >
   Append Data. This adds one example row so you can see the layout. Delete it later.

Limits to know: a data table holds 10,000 rows and 50 fields. Export and purge the log periodically
(see Operating notes).

## Step 2. Import the two data actions (5 min)

1. Admin > Integrations > **Actions** > **Import**.
2. Select `genesys/1-data-actions/Get Conversation Drop Details.json`, choose your Genesys Cloud
   Data Actions integration, click Import Action.
3. The action name is taken from the file name. Confirm it reads exactly
   `Get Conversation Drop Details`, then **Save & Publish**.
4. Repeat for `Write Dropped Call Log Row.json` (name must be `Write Dropped Call Log Row`).
5. Test the first action: open it > Setup > Test, enter any recent conversation ID, click
   Test. You should see `errorCode`, `errorMessage`, `queueName`, `agentName`, `callStartTime`,
   `callEndTime` in the output. Empty strings are normal when the call had no error attribute.

### The error attribute names

The lookup reads the participant attributes named **`ErrorCode`** and **`ErrorMessage`**. Your
flows set them with a *Set Participant Data* action (for example in the flow's error handling
task). If your flows use different attribute names, change these two lines in
`Get Conversation Drop Details.json` before importing (or edit them in the action's
Configuration > Response tab afterwards):

```
"errorCodes":    "$.participants[*].attributes.ErrorCode",
"errorMessages": "$.participants[*].attributes.ErrorMessage",
```

Only the part after `attributes.` changes. The `[*]` means the attribute is found whichever
participant it was set on.

## Step 3. Import the workflow (5 min)

1. Admin > Architect > Flows: **Workflow** > **Add**. Name it `Dropped Call Monitor`, click
   Create Flow.
2. Open the arrow next to **Save** > **Import** > select
   `genesys/3-workflow/Dropped Call Monitor.i3WorkFlow` > Import.
3. Check the two *Call Data Action* blocks (`Get conversation drop details` and
   `Write Dropped Call Log row`). If one shows a validation error, open it and re-select the
   Category (your integration name) and the Action from the drop-downs. The input and output
   mappings are kept.
4. In the **Resources > Data** panel (flow variables), set the **default value** of
   `Flow.logTableId` to the data table ID you copied in Step 1.
5. Leave `Flow.logWhenNoErrorAttribute` at `false` (see Operating notes for what `true` does).
6. **Save**, then **Publish**.
7. Copy the workflow ID from the URL (`.../workflow/flows/<ID>/...`) for Step 4.

If the Architect import rejects the file, use the Archy fallback below. The logic is identical.

### Fallback: Archy

[Archy](https://developer.genesys.cloud/devapps/archy/) is the free Genesys command-line tool that
creates flows from YAML. After `archy setup` with an OAuth client:

```
archy create --file "genesys/3-workflow/Dropped Call Monitor.yaml"
```

Edit `Flow.logTableId` in the YAML first (search for `REPLACE_WITH_DATA_TABLE_ID`).

### What the workflow does, action by action

| # | Action | Detail |
|---|---|---|
| 1 | Call Data Action `Get conversation drop details` | Input `CONVERSATION_ID` = `Flow.conversationId`. Outputs the error attributes, queue, agent, times. Success sets `LookupStatus = OK`. Failure or timeout set `LOOKUP_FAILED` / `LOOKUP_TIMEOUT` and an explanatory message, and the call is still logged so the problem is visible. |
| 2 | Update Data `Classify drop category` | Maps the raw `disconnectType` to a readable label (`Platform error (ERROR)`, `System disconnect (SYSTEM)`, ...). |
| 3 | Decision `No error attribute on the call?` | `IsNotSetOrEmpty(Flow.errorCode)`. If there is no error attribute, a second decision ends the workflow with exit reason `NoErrorAttribute`, unless `Flow.logWhenNoErrorAttribute` is `true` or the lookup failed. |
| 4 | Call Data Action `Write Dropped Call Log row` | Posts one row keyed by the conversation ID. Failure ends with `LogWriteFailed` (for example a duplicate key if the same conversation fires twice). |
| 5 | End Workflow | Exit reason `Logged`. |

Input variables (`Flow.conversationId`, `participantId`, `sessionId`, `disconnectType`,
`mediaType`, `direction`, `ani`, `dnis`, `provider`) are named exactly like the top-level fields of
the `customer.end` event, which is how the trigger passes them in.

## Step 4. Create the trigger (5 min)

Admin > **Triggers** > Event Based Triggers > **Add Trigger**:

| Field | Value |
|---|---|
| Name | `Dropped Call Monitor - our-side voice drops` |
| Topic Name | `v2.detail.events.conversation.{id}.customer.end` |
| Workflow Target | `Dropped Call Monitor` |
| Data Format | `TopLevelPrimitives` |
| Condition 1 | JSON Path `mediaType`, Operator `Equal`, Value `VOICE` |
| Condition 2 | JSON Path `disconnectType`, Operator `In`, Values `["ERROR","SYSTEM","TIMEOUT","TRANSPORT_FAILURE"]` |
| Timing | Default |

Values are case-sensitive and the event uses upper case. Then:

1. **Save & Test**: paste the contents of `genesys/4-trigger/sample-test-event.json` and click
   Test. Both conditions should report a match. Change `disconnectType` to `ENDPOINT` and test
   again: it must not match.
2. Switch the toggle to **Active** and Save.

Prefer the API? `genesys/4-trigger/Dropped Call Monitor - trigger.json` is the exact request body
for `POST /api/v2/processautomation/triggers` in the Developer Tools API Explorer inside Genesys
Cloud. Replace `REPLACE_WITH_WORKFLOW_ID` and set `"enabled": true` when ready.

### Which disconnect types count as "our end"

`disconnectType` on the customer session says who ended the customer's leg:

| Value | Meaning | In the filter? |
|---|---|---|
| `ENDPOINT` | The customer hung up | No (customer end) |
| `ERROR` | Ended because of a platform error | Yes |
| `SYSTEM` | Ended by the system (for example an IVR *Disconnect* after a flow error, or platform cleanup) | Yes |
| `TIMEOUT` | Ended by a timeout | Yes |
| `TRANSPORT_FAILURE` | Media or network transport failure | Yes |
| `PEER` | The other participant (agent or IVR) hung up on the customer | No by default: normal agent hang-ups would flood the log. Add it if your IVR error handling disconnects this way. |
| `CLIENT` | Ended by a client application or API call | No by default |
| `TRANSFER`, `*_TRANSFER`, `SPAM`, `UNCALLABLE`, `OTHER`, `UNKNOWN` | Transfers, outbound, misc. | No |

To widen the filter, add values to Condition 2. The workflow already labels `PEER` and `CLIENT`
if you do.

## Step 5. Verify end to end

1. In a test inbound flow, add *Set Participant Data* with `ErrorCode = TEST` and
   `ErrorMessage = manual test`, followed by a *Disconnect* action, and call it.
2. Within about a minute a row should appear in Admin > Architect > Data Tables > Dropped Call Log,
   keyed by the conversation ID, with `LookupStatus = OK`.
3. If no row appears, see Troubleshooting. To see what the trigger actually received, temporarily set
   `Flow.logWhenNoErrorAttribute` to `true`: every our-side drop is then logged, which shows you the
   real `disconnectType` values your platform produces.

## Operating notes

- **Review**: open the data table, sort by `CallStartTime`, set `Reviewed = Yes` as you work
  through rows. Click the ConversationId to copy it and search it in Performance > Interactions
  for the full timeline and recording.
- **Export**: Data Tables > select the table > Export Data gives you a CSV for Excel or BI.
- **Housekeeping**: tables cap at 10,000 rows. Export, then Manage Imports > Replace All Data with an
  empty template (Import Template) to purge. Do this monthly or when the row count approaches the cap.
- **Tuning without re-importing anything**:
  - Add or remove disconnect types in the trigger condition.
  - `Flow.logWhenNoErrorAttribute = true` logs all our-side drops even without the attribute.
  - Change the attribute names in the lookup action's Response configuration.
- **Duplicate key**: `customer.end` fires once per customer session. In rare conference or transfer
  shapes a conversation can produce two events; the second write fails with a duplicate-key error
  and the workflow ends with `LogWriteFailed`. The first row is kept.
- **Privacy**: Genesys documents data tables as intended for configuration data. ANI is stored here
  for investigation; if that conflicts with your data policy, remove the `ANI` input mapping in the
  write action (and the column).

## Troubleshooting

| Symptom | Check |
|---|---|
| Trigger never fires | Trigger is Active; topic is `customer.end`; conditions use upper-case values; the workflow is **published**. Test with the sample event. |
| Rows have `LookupStatus = LOOKUP_FAILED` | Test `Get Conversation Drop Details` in Admin > Integrations > Actions with the conversation ID from the row. A 403 means the OAuth client lacks `Conversation > Communication > View`. |
| Workflow ends with `LogWriteFailed` | Test `Write Dropped Call Log Row` with `TABLE_ID` = your table ID and `KEY` = any text. A 403 means missing `Architect > Data Table Row > Add`. A 400 usually means a field name in the request body does not match a table API Field ID. A 409 is a duplicate key. |
| `errorCode` is always empty although flows set it | The attribute name differs: compare it with the two JSONPath lines in the lookup action. |
| Architect import error | Use the Archy YAML fallback, or rebuild the 12 actions by hand from the table in Step 3. |

## Regenerating the workflow file

`Dropped Call Monitor.i3WorkFlow` is produced by `tools/build_i3workflow.py` (Python 3, no
dependencies). The readable JSON next to it (`.decoded.json`) is the exact content of the import
file. Run the script again after editing the generator to change the workflow.
