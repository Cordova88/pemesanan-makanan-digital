# Technical Design Document

## Gemini AI Integration for the Django Restaurant Recommendation System

**Project:** Digital Restaurant Ordering System
**Framework:** Django / Python
**AI Provider:** Google Gemini API
**Integration Pattern:** Local-first, AI-assisted natural-language interpretation
**Status:** Implementation specification — not yet fully integrated

---

# 1. Purpose

The purpose of Gemini integration is to improve the restaurant recommendation chatbot's ability to understand Indonesian natural language, informal expressions, ambiguous food preferences, and conversational requests that the existing rule-based interpreter cannot confidently understand.

Gemini will supplement the existing recommendation system rather than replace it.

The application already has a local interpreter, conversation management, recommendation ranking, and cart integration. These components should remain the foundation of the system.

The integration must preserve the following principles:

1. Existing local interpretation continues to handle familiar messages.
2. Gemini is called only when local interpretation returns `UNKNOWN` in the initial implementation.
3. Gemini interprets the customer's message into structured data rather than selecting actual menu items.
4. Django validates all AI-generated data before using it.
5. Existing services remain responsible for recommendations, conversation state, and cart operations.
6. The chatbot continues to function when Gemini is unavailable.

## 1.1 Main objective

Improve language understanding without transferring application control or business decisions to an AI model.

For example, a customer might say:

> "Aku pengen makanan yang nampol, tapi jangan terlalu berat."

The local interpreter might not understand the entire expression.

Gemini can interpret the customer's likely meaning as structured preferences. Django then validates those preferences and passes them through the existing recommendation system.

Gemini should not independently invent a dish, determine its price, or claim that it is available.

---

# 2. Existing System Context

The Gemini integration must reuse the current application architecture.

| Existing component        | Responsibility                                                     |
| ------------------------- | ------------------------------------------------------------------ |
| `ConversationInterpreter` | Interprets messages using deterministic rules                      |
| `ChatbotService`          | Orchestrates conversation flow and applies interpreted preferences |
| `TagExtractor`            | Recognizes supported food tags and aliases                         |
| `MoodExtractor`           | Recognizes supported customer moods                                |
| `MoodResolver`            | Converts moods into recommendation characteristics                 |
| `RecommendationService`   | Ranks actual menu items from the database                          |
| `CartService`             | Manages the customer's session-based cart                          |
| Django models             | Store authoritative menu, price, availability, and order data      |

The existing interpreter returns a Python `ConversationInterpretation` object. Its fields include:

* `intent`
* `operations`
* `tags`
* `excluded_tags`
* `soft_excluded_tags`
* `moods`
* `max_price`
* `category`
* `prefer_affordable`
* `last_question`
* `contextual_reference`
* `message_is_meaningful`
* `follow_up`
* `clear_moods`

Preference changes are represented by `PreferenceOperation`, with actions such as `ADD`, `REMOVE`, `REPLACE`, `KEEP`, and `CLEAR`.

These existing structures are the integration target. Gemini should not introduce a separate, competing conversation format throughout the application.

## 2.1 Repository map: where each part lives

Use this section as the code-navigation guide before implementing the integration. The paths and behavior below describe the current repository, not a proposed future layout.

| If you need to find... | Look here | What goes in / what comes out |
| --------------------- | ---------- | ----------------------------- |
| The customer's message and chat UI | `recommendation/templates/recommendation/chatbot.html` | Sends the message and optional action to `/api/recommendation/chat/`; renders the returned message, preferences, quick replies, and recommendation cards. |
| The HTTP adapter for chat | `recommendation/views.py`, `chat()` | Reads the JSON request and Django session, calls `ChatbotService.reply()`, then converts recommendation matches and internal preference tags into public JSON. |
| The URL that connects the browser to the chat view | `config/urls.py`, `recommendation/urls.py` | `/api/recommendation/chat/` resolves to `recommendation.views.chat`. The page itself is served through `recommendation/urls_page.py` at `/chatbot/`. |
| Conversation routing and session state | `recommendation/services/chatbot.py`, `ChatbotService.reply()` | Receives the message, `more` flag/action, and session-backed context. Calls the local interpreter, updates preferences/session state, asks follow-ups, and invokes the recommender. |
| Local intent and preference interpretation | `recommendation/services/conversation_interpreter.py`, `ConversationInterpreter.interpret()` | Receives message text plus optional last-question/recommendation context; returns a `ConversationInterpretation`, including its intent, operations, tags, moods, and budget/category fields. |
| Meaning of preference state and serialization | `recommendation/services/tag_extractor.py`, `Preferences` | Defines the preference fields, conversion to/from session dictionaries, and direct tag/negative-preference extraction. This is the existing state shape that the AI result must eventually feed. |
| Accepted tag vocabulary and Indonesian display labels | `recommendation/services/tag_extractor.py` and `recommendation/services/language.py` | The extractor defines known aliases; `TAG_LABELS` maps internal identifiers to customer-facing labels. Use internal identifiers in validated interpretation data, not display labels. |
| Mood vocabulary and mood-to-tag mapping | `recommendation/services/mood_extractor.py` and `recommendation/services/mood_resolver.py` | The extractor returns recognized mood identifiers; the resolver maps those identifiers to recommendation tags. Keep this distinction when designing AI output. |
| Ranking actual database menus | `recommendation/services/recommendation.py`, `RecommendationService.rank()` | Receives validated `Preferences`; reads active, available `MenuItem` records and their tags; returns `RecommendationMatch` objects. Gemini should not return menu items or replace this lookup. |
| Authoritative menu/tag data | `menu/models.py` | `MenuItem`, `MenuTag`, and their relation define menu identity, availability, price, category, and assigned tags. |
| Add-to-cart behavior after a recommendation | `recommendation/views.py`, `add_to_cart()`; `cart/services.py` | The browser submits the selected real menu ID and options to `/api/recommendation/add/`; the existing `CartService` validates and updates the cart. This is downstream of language interpretation. |
| Existing regression tests | `recommendation/tests.py` | Covers local interpretation, recommendation ranking, session/conversation behavior, API responses, and chatbot-to-cart/order behavior. Add AI tests here or in a dedicated recommendation test module, mocking the provider boundary. |
| Provider dependency and configuration | `requirements.txt`, `.env.example`, `config/settings.py` | `google-genai` is listed as a dependency and `.env.example` contains a placeholder. Current `config/settings.py` does not yet define Gemini settings or read `GEMINI_API_KEY`; confirm how environment variables are loaded before relying on `.env`. |

### Current end-to-end data path

```text
chatbot.html
  -- message/action JSON -->
config URL routing
  --> recommendation.views.chat()
  --> ChatbotService.reply(message, more/action)
  --> ConversationInterpreter.interpret(message, conversation context)
  --> ConversationInterpretation
  --> ChatbotService applies operations to Preferences and session state
  --> RecommendationService.rank(Preferences)
  --> database MenuItems / MenuTags
  --> recommendation.views serializes the result to JSON
  --> chatbot.html renders the cards
```

The selected card follows a separate path: the browser posts its menu ID and selected variants/add-ons to `recommendation.views.add_to_cart()`, which delegates to the existing `CartService`.

### Where a future Gemini fallback connects

There is currently **no Gemini call in the active chat request path**. `recommendation.views.chat()` calls `ChatbotService`; `ChatbotService` constructs and calls `ConversationInterpreter`, and the current `recommendation/services/gemini.py` is not imported by those active call sites. Treat the Gemini flow in this document as planned until that wiring and its tests exist.

For the local-first design described here, the integration point is inside `ChatbotService.reply()`: after the local interpretation has been produced and before the existing `UNKNOWN` response is returned. Keep the local handling for reset, greetings, help, out-of-scope messages, rejection, and recommendation references on their existing paths. Only eligible unknown food requests should be considered for the provider; an unknown result alone does not prove that a message is a food request.

The data hand-off should be:

1. Start from the current message and the minimal conversation context needed to interpret it; the service already reads `last_question` and recent recommendation IDs from the session.
2. Have the provider boundary return raw provider output, not session changes or menu data.
3. Validate and normalize that output against the actual supported tag/mood identifiers and allowed intent/operation semantics.
4. Convert accepted data into the existing `ConversationInterpretation` shape.
5. Let the existing `ChatbotService` apply its `PreferenceOperation` values, update `Preferences` and session state, then continue through `RecommendationService`.
6. On unavailable provider, malformed output, or rejected fields, retain the current local clarification behavior and do not mutate saved preferences.

Use the tables above to trace a field end to end. For example, to add an AI-extracted mood, confirm the valid mood identifiers in `MoodExtractor`, how `MoodResolver` maps them, how `Preferences` stores them, and how `RecommendationService.rank()` uses the resolved tags. To add a response field, also check `recommendation/views.py` and the browser renderer so it is actually exposed and consumed.

---

# 3. Proposed Architecture

## 3.1 High-level flow

```text
Customer Message
       |
       v
ChatbotService
       |
       v
ConversationInterpreter
       |
       +---- Recognized intent ----> Existing local flow
       |
       +---- UNKNOWN
                 |
                 v
          GeminiInterpreter
                 |
                 v
            GeminiClient
                 |
                 v
            Gemini API
                 |
                 v
          Structured JSON
                 |
                 v
       Validate and normalize
                 |
                 v
    ConversationInterpretation
                 |
                 v
          ChatbotService
                 |
                 v
      RecommendationService
                 |
                 v
       Actual database items
                 |
                 v
        Chatbot response
```

The diagram represents the intended logical flow. In the implementation, `GeminiInterpreter` may call `GeminiClient` internally to send the request and process its response.

## 3.2 Architectural boundary

**Gemini understands language. Django controls the application.**

Gemini may identify what the customer probably means. Django determines whether that interpretation is valid and what operations are permitted.

Gemini must not directly:

* Query or modify Django models.
* Choose fictional menu items.
* Determine authoritative menu prices or availability.
* Modify the shopping cart.
* Create orders.
* Mark orders as paid.
* Cancel or refund orders.
* Modify the conversation session directly.
* Override application validation.

All resulting actions must go through the existing Django services.

---

# 4. OOP Design and Responsibilities

The implementation should follow the existing project's service-oriented structure and avoid unnecessary architectural changes.

## 4.1 `GeminiClient`

**Suggested file:** `recommendation/services/gemini.py`

Responsibility: communicate with the Gemini API.

It should handle:

* Reading the configured API key and model settings.
* Building and sending the provider request.
* Applying a reasonable request timeout where supported.
* Receiving the model response.
* Reporting provider errors through a predictable internal interface.

It should not handle:

* Food-tag interpretation rules.
* Preference updates.
* Recommendation ranking.
* Database queries.
* Cart or order operations.
* Conversation state.

Conceptual interface:

```python
class GeminiClient:
    def generate(self, prompt):
        """Send a prompt to Gemini and return the response."""
```

This is illustrative, not a requirement to copy the code exactly. The method signature should match the chosen SDK and response format.

## 4.2 `GeminiInterpreter`

**Suggested file:** `recommendation/services/ai/interpreter.py`

Responsibility: interpret the Gemini response and convert it into a validated application-level result.

It should:

1. Receive the current message and any strictly necessary context.
2. Build the interpretation instructions.
3. Call `GeminiClient`.
4. Parse the structured response.
5. Validate intents, tags, moods, types, and field combinations.
6. Convert the accepted result into `ConversationInterpretation`.
7. Report invalid or failed interpretation without mutating conversation state.

It must not rank menu items or update the cart.

## 4.3 `ConversationInterpreter`

Responsibility: preserve deterministic, rule-based interpretation.

It remains the first interpreter in the initial integration. Its existing behavior should not be replaced merely because Gemini is available.

## 4.4 `ChatbotService`

Responsibility: orchestrate the request.

The service should:

1. Invoke `ConversationInterpreter`.
2. Check whether the result is `UNKNOWN`.
3. Call `GeminiInterpreter` only when eligible.
4. Use the accepted interpretation through the existing conversation flow.
5. Preserve current recommendation and cart integration.
6. Leave stored preferences unchanged if interpretation fails.

The chatbot should not need to know how HTTP requests to Google's API work.

## 4.5 `RecommendationService`

Responsibility: rank real menu items using the existing validated preferences.

No AI-generated menu list should bypass this service.

## 4.6 Suggested package structure

```text
recommendation/
    services/
        chatbot.py
        conversation_interpreter.py
        recommendation.py
        tag_extractor.py
        mood_extractor.py
        mood_resolver.py
        language.py
        gemini.py
        ai/
            __init__.py
            interpreter.py
```

The existing `gemini.py` can remain at its current location for the first implementation. Do not move files solely to match this example. If the AI integration grows, the structure can be refactored deliberately.

---

# 5. Request Routing Policy

## 5.1 Initial rule: local first

The first version should use the local interpreter as the default.

| Customer message                                   | Expected route                                                      |
| -------------------------------------------------- | ------------------------------------------------------------------- |
| "Aku mau pedas"                                    | Local interpreter                                                   |
| "Jangan pedas"                                     | Local interpreter                                                   |
| "Ganti ayam jadi sapi"                             | Local interpreter                                                   |
| "Reset"                                            | Local interpreter                                                   |
| "Cari yang lain"                                   | Local interpreter                                                   |
| "test"                                             | Local `UNKNOWN` handling, subject to the fallback eligibility rules |
| An unfamiliar, meaningful food request             | Gemini fallback when local interpretation returns `UNKNOWN`         |
| An unrelated request about programming or politics | Local out-of-scope response; no Gemini call                         |

The exact routing rules must be tested against the existing `ConversationInterpreter`. Do not assume every example currently produces the specified intent without checking the code.

## 5.2 Do not send every message to Gemini

Sending every customer message to Gemini would introduce unnecessary API calls and make behavior less predictable.

Local-first routing provides:

* Lower API usage.
* Faster responses for familiar requests.
* Deterministic handling of known commands.
* Easier testing.
* Reduced dependency on provider availability.
* A clear explanation of why AI is part of the project.

## 5.3 Unknown does not always mean eligible for AI

An `UNKNOWN` result can represent different situations. For example, the customer may have sent gibberish, an unrelated question, or a meaningful food request expressed unusually.

Before enabling fallback, distinguish between:

* Unknown but potentially meaningful food-related messages.
* Obviously meaningless messages.
* Clearly out-of-scope requests.

The last two categories should receive local responses without calling Gemini.

For the first version, implement this conservatively. A more sophisticated confidence-based router can be considered later.

---

# 6. Gemini Response Contract

Gemini must return a small, predictable JSON object. It should contain only fields needed to interpret the current message.

The JSON is a transport format, not the application's domain model.

## 6.1 Proposed initial schema

```json
{
  "intent": "RECOMMEND",
  "tags": ["filling"],
  "excluded_tags": [],
  "soft_excluded_tags": [],
  "moods": [],
  "message_is_meaningful": true
}
```

This is an illustrative response for a request that can reasonably be interpreted as wanting filling food.

The actual interpretation must depend on the customer's wording. Gemini should not add preferences that the customer did not express or that cannot reasonably be inferred.

### Field definitions

| Field                   | Purpose                                                                   |
| ----------------------- | ------------------------------------------------------------------------- |
| `intent`                | Describes the preference-related request                                  |
| `tags`                  | Supported food characteristics the customer wants                         |
| `excluded_tags`         | Strongly unwanted characteristics                                         |
| `soft_excluded_tags`    | Characteristics the customer would prefer to avoid but may tolerate       |
| `moods`                 | Recognized contextual moods                                               |
| `message_is_meaningful` | Indicates whether the message appears to contain an interpretable request |

Initially, omit `max_price`, `category`, `prefer_affordable`, `last_question`, `contextual_reference`, `follow_up`, and `clear_moods` unless the implementation demonstrates a concrete need to support them. Existing local parsing should continue to handle explicit budgets and established conversation control.

## 6.2 Allowed intents

Start with the preference-related intents compatible with the existing application:

* `RECOMMEND`
* `UPDATE_PREFERENCES`
* `REMOVE_PREFERENCES`
* `REPLACE_PREFERENCES`
* `UNKNOWN`

Before finalizing the schema, verify the actual intent values and behavior in the existing code. The names in this document must match the project's real constants or strings.

Control-flow actions such as resetting a conversation, rejecting previous recommendations, and selecting a particular recommendation should remain local responsibilities.

## 6.3 Tags and moods

Tags must be restricted to the existing supported vocabulary represented by `TagExtractor`.

Moods must be restricted to the supported non-confusion moods represented by `MoodExtractor`, such as:

* `tired`
* `low_mood`
* `very_hungry`
* `hot_thirsty`
* `quick`

These lists are examples of the project's current taxonomy and must be verified against the actual source code before implementation.

Never accept arbitrary tag or mood strings simply because Gemini returned them.

Mood-derived recommendation tags should continue to be handled by `MoodResolver`.

## 6.4 Preference operations

This is an important design consideration.

The existing application represents preference changes with `PreferenceOperation`. Gemini's response must not contradict the meaning of the requested change.

For example:

**Customer:** "Ganti ayam jadi sapi."

The intended interpretation needs to identify both:

* The new preference: `beef`.
* The preference being replaced: `chicken`.

A response containing only `REPLACE_PREFERENCES` and `["beef"]` would be incomplete if Django cannot determine which existing preference to remove.

There are two possible designs:

1. Gemini returns a validated operation representation that maps to `PreferenceOperation`.
2. Gemini returns a smaller preference representation, and a dedicated Django conversion layer derives the operations.

For the first implementation, prefer the smallest schema that can express the operations actually needed by the existing interpreter. Document which fields are required for each intent and reject contradictory combinations.

Do not allow the model to return arbitrary Python instructions or executable content.

---

# 7. Validation and Conversion

After receiving JSON, Django must validate it before using it.

## 7.1 Validation rules

The validation layer should check:

1. The response can be parsed as JSON.
2. The top-level structure is an object.
3. Required fields exist.
4. Field types are correct.
5. The intent belongs to the allowed set.
6. Every tag belongs to the supported vocabulary.
7. Every mood belongs to the supported vocabulary.
8. Lists contain valid strings and do not exceed reasonable size limits.
9. The field combinations are logically consistent.
10. No unsupported action, menu selection, price claim, or business operation is included.

If a response contains invalid tags or an invalid intent, reject the entire interpretation rather than silently applying a partial result.

## 7.2 Convert to the existing domain object

After validation, Django converts the accepted representation into `ConversationInterpretation`.

For example, JSON arrays can become Python sets where appropriate. Operations must be constructed consistently with the selected intent and the existing preference-update semantics.

Fields that Gemini is not permitted to interpret should receive safe defaults or be derived by existing Django logic.

**Do not let Gemini's JSON directly overwrite the session.** The validated result must go through `ChatbotService` and the established preference-handling flow.

---

# 8. Conversation Context

The application, not Gemini, owns the conversation state.

The existing session-backed context remains authoritative for:

* Current preferences.
* Excluded preferences.
* Current mood.
* Previous recommendations.
* Last question asked.
* Current conversation state.

Gemini should primarily interpret the current message.

If a follow-up cannot be understood without context, provide only the minimal relevant information, such as the last question or a short reference to the current task.

Do not send the entire conversation history by default.

Do not let old preferences become permanent merely because they appeared in an earlier message. A new message must be interpreted on its own terms and then applied through the existing update rules.

---

# 9. Error Handling and Fallback

Gemini is an optional interpretation capability, not a requirement for the ordering system to function.

The following failures must not crash the chatbot:

* Missing API key.
* Invalid API configuration.
* Network or connection failure.
* Request timeout.
* Rate limiting, such as HTTP 429.
* Provider service errors, such as HTTP 503.
* Malformed JSON.
* Invalid intent, tag, or mood.
* Empty or unusable model output.

## 9.1 Expected behavior

```text
Local interpreter returns UNKNOWN
             |
             v
       Gemini fallback
             |
       +-----+------+
       |            |
   Valid result   Failure/invalid
       |            |
       v            v
  Validate and    Local clarification
  convert result  response
       |            |
       v            v
  Existing flow   No preference mutation
```

The fallback response should ask the customer to clarify their food request.

It must not apply guessed preferences or fabricate recommendations merely to avoid returning an error.

Provider details and API keys must not be exposed to customers.

---

# 10. Security and Resource Limits

## 10.1 API key

Store the Gemini API key in an environment variable, for example:

`GEMINI_API_KEY`

Read it through Django settings or the project's existing configuration approach.

Requirements:

* Never hardcode the actual key in Python.
* Never send the key to browser JavaScript.
* Never commit the key to Git.
* Keep `.env` excluded from version control.
* Document the required variable in `.env.example` using a placeholder only.
* Handle missing configuration gracefully.

## 10.2 Usage limits

Add configurable controls before enabling the integration broadly.

Suggested initial values:

| Setting                          |                             Example starting value |
| -------------------------------- | -------------------------------------------------: |
| Maximum message length           |                                     500 characters |
| Maximum Gemini calls per session |                                                  5 |
| Provider timeout                 | A short, configurable limit appropriate to the SDK |

These are starting values for testing, not universal requirements.

The call limit should count actual provider calls, not every chatbot message. The backend must enforce it; a frontend-only limit is insufficient.

A session limit alone is not a complete abuse-prevention system. Additional request throttling may be needed if the public endpoint is exposed widely.

---

# 11. Testing Strategy

Tests should verify the integration's behavior without relying on live Gemini API calls.

Mock the API boundary so tests are deterministic, fast, and free of API charges.

## 11.1 Gemini client tests

Test:

* Valid configuration.
* Missing API key.
* Successful provider response.
* Provider error.
* Timeout or connection failure.
* Unexpected response format.

## 11.2 Gemini interpreter tests

Test:

* Valid structured response.
* Malformed JSON.
* Missing required fields.
* Invalid intent.
* Unknown tag.
* Unknown mood.
* Incorrect field types.
* Contradictory operations.
* Response that includes unsupported fields or actions.
* Valid response converts to the expected `ConversationInterpretation`.

## 11.3 Routing tests

Verify that:

* Known local messages do not call Gemini.
* Reset and recommendation-rejection behavior remains local.
* Eligible unknown messages can call Gemini.
* Gibberish does not unnecessarily trigger Gemini.
* Clearly out-of-scope messages do not trigger Gemini.
* A valid Gemini interpretation enters the normal conversation flow.
* A failed Gemini call leaves existing preferences unchanged.

## 11.4 Regression tests

Run the existing Django test suite after every implementation stage.

The Gemini integration must not break:

* Menu recommendations.
* Preference changes.
* Mood interpretation.
* Session context.
* Cart operations.
* Checkout and order creation.
* Existing customer-facing responses.

Useful commands:

```bash
python manage.py check
python manage.py test
```

Use the project's actual test structure and targeted test labels where helpful.

---

# 12. Implementation Roadmap

Implement the feature incrementally. Do not connect the API, redesign the conversation interpreter, and change the frontend in one step.

## Part 2A — Gemini Infrastructure

**Goal:** establish a working, isolated Gemini API boundary.

Tasks:

1. Inspect the existing `gemini.py` and installed `google-genai` dependency.
2. Configure the API key and model through environment variables and Django settings.
3. Implement `GeminiClient`.
4. Send a small test prompt from the Django backend.
5. Handle missing configuration and provider failures.
6. Write mocked client tests.

**Completion criteria:** Django can communicate with Gemini through a dedicated service. The chatbot's behavior remains unchanged.

## Part 2B — Structured Interpreter

**Goal:** convert natural language into validated structured data.

Tasks:

1. Finalize the JSON response contract.
2. Define allowed intents, tags, moods, and operation semantics.
3. Write the interpretation prompt.
4. Request structured output using the chosen SDK's supported capabilities.
5. Parse and validate the response.
6. Convert the accepted result to `ConversationInterpretation`.
7. Add interpreter tests.

**Completion criteria:** the interpreter produces a validated application object or a controlled failure. It cannot choose menu items or execute business actions.

## Part 2C — Local-First Routing

**Goal:** connect the Gemini interpreter to the existing chatbot.

Tasks:

1. Keep `ConversationInterpreter` as the first step.
2. Identify which `UNKNOWN` messages are eligible for fallback.
3. Call `GeminiInterpreter` for eligible messages.
4. Send valid results through the existing `ChatbotService` flow.
5. Preserve local handling for recognized commands.
6. Add tests verifying routing behavior.

**Completion criteria:** known messages work as before, while eligible unfamiliar food requests can benefit from Gemini.

## Part 2D — Safety and Failure Handling

**Goal:** make the integration resilient and controlled.

Tasks:

1. Enforce message length limits.
2. Enforce per-session API call limits.
3. Handle provider errors, timeouts, and malformed responses.
4. Reject invalid structured output.
5. Prevent session mutation on interpretation failure.
6. Verify API key security and logging practices.
7. Add tests for failure cases.

**Completion criteria:** Gemini failures never crash the chatbot or cause unvalidated preference changes.

## Part 2E — Full Integration and Browser Verification

**Goal:** validate the complete customer experience.

Test at least:

1. Normal local recommendation.
2. Ambiguous Indonesian food request.
3. Preference addition and removal.
4. Replacing chicken with beef.
5. Rejecting existing recommendations.
6. Gibberish and unrelated questions.
7. Gemini API failure.
8. A customer continuing after a failed interpretation.
9. Cart integration and existing checkout behavior.
10. Mobile browser layout and usability.

**Completion criteria:** the hybrid chatbot behaves correctly from customer message to recommendation, while the existing ordering system remains intact.

## Part 3 — AI Usage Monitoring

Treat this as a later enhancement rather than a prerequisite.

Possible features include:

* Counting Gemini calls.
* Recording successful interpretations and failures.
* Recording fallback usage.
* Measuring request latency.
* Monitoring rate-limit and provider errors.
* Displaying usage summaries in the staff CMS.

If detailed logs are added, minimize stored customer text and avoid recording API keys or unnecessary personal information. Do not claim that the CMS knows the exact remaining provider quota unless an authoritative source provides that information.

---

# 13. README and Documentation Updates

After the integration works, update the README to explain:

* What Gemini contributes.
* Why the system uses local-first routing.
* How to configure the API key.
* Which environment variables are required.
* What happens when Gemini is unavailable.
* How to run the tests.
* What Gemini is prohibited from doing.

The README should describe the implemented behavior, not features that remain planned.

---

# 14. OOP Justification for the University Project

The integration provides a practical example of separation of responsibility.

* **Encapsulation:** validation and provider communication are controlled by dedicated services.
* **Abstraction:** `ChatbotService` uses the interpreter's result without needing to manage Gemini's HTTP/API details.
* **Single responsibility:** `GeminiClient` communicates with the provider; `GeminiInterpreter` interprets and validates its output; `RecommendationService` ranks menu items.
* **Composition:** `ChatbotService` coordinates the interpreter and recommendation services.
* **Separation of concerns:** natural-language interpretation is separated from business logic.

A suitable explanation for a lecturer is:

> "Gemini is used as an additional natural-language interpretation layer. The local interpreter handles familiar requests, while Gemini helps interpret eligible messages that the rule-based system cannot understand. The AI output is validated and converted into the application's existing interpretation object. Django remains responsible for preference updates, menu recommendations, cart operations, and order processing."

This demonstrates that AI is integrated into an existing OOP system rather than being allowed to replace its application logic.

---

# 15. Final Acceptance Criteria

The integration is complete when:

* [ ] Gemini is configured only on the server.
* [ ] The API key is not exposed or committed.
* [ ] `GeminiClient` is independent of menu and cart business logic.
* [ ] `GeminiInterpreter` returns validated data or a controlled failure.
* [ ] The JSON contract maps cleanly to `ConversationInterpretation`.
* [ ] Known local requests do not unnecessarily call Gemini.
* [ ] Eligible unfamiliar food requests can use Gemini.
* [ ] Out-of-scope requests are handled locally.
* [ ] Invalid AI output cannot mutate preferences.
* [ ] Provider failures do not crash the chatbot.
* [ ] Existing recommendation, cart, and checkout behavior remains intact.
* [ ] Tests cover normal operation, routing, validation, and failures.
* [ ] README documentation reflects the actual implementation.

**The central design rule is simple: Gemini interprets the customer's meaning; the Django application validates that meaning and decides what happens next.**
