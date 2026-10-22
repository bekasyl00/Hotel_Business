<script setup>
import { computed, ref, watch, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useSessionStore } from "@/entities/session";
import { useResortStore } from "@/entities/resort";
import { useBookingStore } from "@/entities/booking";
import { StaffShell } from "@/widgets/staff-shell";
import { Overview } from "@/widgets/overview";
import { ResortEditor } from "@/features/edit-resort";
import { RoomEditor } from "@/features/edit-room";
import { TariffEditor } from "@/features/edit-tariff";
import { AccountEditor } from "@/features/edit-account";
import { BookingEditor } from "@/features/create-booking";
import { Modal } from "@/shared/ui";
import { request } from "@/shared/api";
import { money, dateLabel, timeLabel, statusNames } from "@/shared/lib";
import { isDemo } from "@/shared/config";
const session = useSessionStore(),
  catalog = useResortStore(),
  bookings = useBookingStore();
const route = useRoute(),
  router = useRouter();
const section = computed(() => route.params.section || "overview");
const titles = {
  overview: "Обзор работы",
  resorts: "Санатории",
  rooms: "Номерной фонд",
  tariffs: "Тарифы и услуги",
  bookings: "Бронирования",
  history: "История изменений",
  accounts: "Управляющие",
};
const subtitles = {
  overview: "Всё важное для вашей команды — на одном экране.",
  resorts: "Карточки, расположение и публикация на сайте.",
  rooms: "Каждая комната и её доступность для бронирования.",
  tariffs: "Форматы отдыха и доплаты к стоимости проживания.",
  bookings: "Заезды, ручные брони и отмены.",
  history: "Кто, когда и что изменил в данных.",
  accounts: "Доступ управляющего к одному санаторию.",
};
const selected = ref(""),
  query = ref(""),
  status = ref("all"),
  loading = ref(true),
  error = ref(""),
  notice = ref(""),
  accounts = ref([]),
  audit = ref([]),
  editor = ref(null),
  confirm = ref(null),
  busy = ref(false);
const current = computed(() =>
  catalog.resorts.find((r) => r.id === selected.value),
);
const scopedRooms = computed(() =>
  catalog.rooms.filter((r) => r.resortId === selected.value),
);
const scopedTariffs = computed(() =>
  catalog.tariffs.filter((t) => t.resortId === selected.value),
);
const scopedBookings = computed(() =>
  bookings.items.filter((b) => b.resortId === selected.value),
);
const matches = (item) =>
  Object.values(item)
    .filter((v) => typeof v === "string")
    .join(" ")
    .toLocaleLowerCase()
    .includes(query.value.toLocaleLowerCase());
const filteredResorts = computed(() =>
  catalog.resorts
    .filter(matches)
    .filter((r) => status.value === "all" || r.status === status.value),
);
const filteredRooms = computed(() =>
  scopedRooms.value
    .filter(matches)
    .filter((r) => status.value === "all" || r.status === status.value),
);
const filteredTariffs = computed(() =>
  scopedTariffs.value
    .filter(matches)
    .filter((r) => status.value === "all" || r.status === status.value),
);
const filteredBookings = computed(() =>
  scopedBookings.value
    .filter(matches)
    .filter((r) => status.value === "all" || r.status === status.value)
    .slice()
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
);
const filteredAudit = computed(() =>
  audit.value.filter(
    (a) =>
      (!selected.value ||
        a.resortId === selected.value ||
        (session.isAdmin && a.resortId === null)) &&
      matches(a),
  ),
);
const filteredAccounts = computed(() => accounts.value.filter(matches));
const canAdd = computed(() =>
  ["resorts", "accounts"].includes(section.value)
    ? session.isAdmin
    : ["rooms", "tariffs", "bookings"].includes(section.value) &&
      current.value &&
      current.value.status !== "archived",
);
const addLabels = {
  resorts: "Создать санаторий",
  rooms: "Добавить номер",
  tariffs: "Добавить тариф",
  bookings: "Добавить бронирование",
  accounts: "Добавить управляющего",
};
let generation = 0;
async function load() {
  const run = ++generation;
  loading.value = true;
  error.value = "";
  try {
    await session.restore();
    if (!session.user) return router.replace("/staff/login");
    const data = await request("GET", "/workspace");
    if (run !== generation) return;
    catalog.setData(data);
    bookings.items = data.bookings;
    accounts.value = data.accounts;
    audit.value = data.audit;
    if (!catalog.resorts.some((r) => r.id === selected.value))
      selected.value =
        catalog.resorts.find((r) => r.status !== "archived")?.id ||
        catalog.resorts[0]?.id ||
        "";
  } catch (e) {
    if (run === generation) error.value = e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
async function logout() {
  try {
    await session.logout();
    catalog.clear();
    bookings.items = [];
    await router.replace("/staff/login");
  } catch (e) {
    error.value = e.message;
  }
}
function open(kind = section.value, item = null) {
  notice.value = "";
  editor.value = { kind, item };
}
async function saved(record) {
  editor.value = null;
  notice.value = "Изменения сохранены.";
  if (section.value === "resorts" && record?.id) selected.value = record.id;
  await load();
}
async function act() {
  busy.value = true;
  try {
    const { kind, item } = confirm.value;
    await request(
      kind === "bookings" ? "PATCH" : "DELETE",
      `/${kind}/${item.id}`,
      {
        version: item.version,
        ...(kind === "bookings" ? { status: "cancelled" } : {}),
      },
    );
    confirm.value = null;
    notice.value = "Готово. Изменение записано в историю.";
    await load();
  } catch (e) {
    confirm.value.error = e.message;
  } finally {
    busy.value = false;
  }
}
function switchResort(id) {
  selected.value = id;
  router.push("/staff/rooms");
}
function changes(entry) {
  const keys = new Set([
    ...Object.keys(entry.before || {}),
    ...Object.keys(entry.after || {}),
  ]);
  return [...keys]
    .filter(
      (k) =>
        !["id", "version", "rating", "ownerId"].includes(k) &&
        JSON.stringify(entry.before?.[k]) !== JSON.stringify(entry.after?.[k]),
    )
    .map((key) => ({
      key,
      before: entry.before?.[key],
      after: entry.after?.[key],
    }));
}
const fieldNames = {
  name: "Название",
  status: "Статус",
  price: "Цена",
  supplement: "Доплата",
  number: "Номер",
  capacity: "Вместимость",
  area: "Площадь",
  lat: "Широта",
  lng: "Долгота",
  address: "Адрес",
  city: "Город",
  description: "Описание",
  subtitle: "Краткое описание",
  feature: "Услуга",
  features: "Услуги",
  beds: "Кровати",
  category: "Категория",
  title: "Название",
  login: "Логин",
  resortId: "Санаторий",
  start: "Заезд",
  end: "Выезд",
  guests: "Гости",
  total: "Сумма",
  guestLabel: "Гость",
  roomId: "Комната",
  tariffId: "Тариф",
};
const display = (value) =>
  value == null
    ? "—"
    : Array.isArray(value)
      ? value.join(", ")
      : statusNames[value] || String(value);
watch(section, () => {
  query.value = "";
  status.value = "all";
  editor.value = null;
});
const storageChanged = (e) => {
  if (e.key === "tynys:workspace:v2") load();
};
onMounted(() => {
  load();
  window.addEventListener("storage", storageChanged);
});
onBeforeUnmount(() => {
  generation++;
  window.removeEventListener("storage", storageChanged);
});
</script>
<template>
  <StaffShell :section="section" @logout="logout"
    ><main class="work-main">
      <div v-if="isDemo" class="demo-strip">
        <span class="demo-dot"></span>Демо-пространство · изменения видны только
        в этом браузере
      </div>
      <div
        v-if="!titles[section] || (section === 'accounts' && !session.isAdmin)"
        class="surface work-empty"
      >
        <h1>Раздел недоступен</h1>
        <p>Откройте один из доступных разделов меню.</p>
        <RouterLink to="/staff/overview">Вернуться к обзору</RouterLink>
      </div>
      <template v-else
        ><div class="work-title">
          <div>
            <span class="eyebrow">{{
              session.isAdmin ? "УПРАВЛЕНИЕ ПЛАТФОРМОЙ" : current?.name
            }}</span>
            <h1>
              {{
                section === "resorts" && !session.isAdmin
                  ? "Мой санаторий"
                  : titles[section]
              }}
            </h1>
            <p>{{ subtitles[section] }}</p>
          </div>
          <button
            v-if="canAdd"
            class="primary"
            :disabled="loading"
            @click="open()"
          >
            ＋ {{ addLabels[section] }}
          </button>
        </div>
        <p v-if="notice" class="success-notice" role="status">✓ {{ notice }}</p>
        <div v-if="error" class="error-panel" role="alert">
          <p>{{ error }}</p>
          <button class="secondary" @click="load">Повторить загрузку</button>
        </div>
        <p v-if="loading" class="loading-panel" role="status">
          Загружаем рабочее пространство…
        </p>
        <template v-else-if="!error"
          ><div
            v-if="['rooms', 'tariffs', 'bookings', 'history'].includes(section)"
            class="context-bar"
          >
            <label
              >Санаторий<select v-model="selected" :disabled="!session.isAdmin">
                <option v-if="!catalog.resorts.length" value="">
                  Санаториев пока нет
                </option>
                <option v-for="r in catalog.resorts" :key="r.id" :value="r.id">
                  {{ r.name }}{{ r.status === "archived" ? " · архив" : "" }}
                </option>
              </select></label
            ><span v-if="current" :class="['status-pill', current.status]">{{
              statusNames[current.status]
            }}</span
            ><span v-if="current" class="context-count"
              >{{ scopedRooms.length }} комнат ·
              {{ scopedTariffs.length }} тарифов</span
            >
          </div>
          <Overview
            v-if="section === 'overview'"
            :resorts="catalog.resorts"
            :rooms="catalog.rooms"
            :bookings="bookings.items"
            @bookings="router.push('/staff/bookings')"
            @create="current ? open('bookings') : router.push('/staff/resorts')"
          />
          <section v-else class="surface">
            <div class="table-toolbar">
              <label class="search-field"
                ><span aria-hidden="true">⌕</span
                ><input
                  v-model="query"
                  type="search"
                  :placeholder="
                    section === 'history'
                      ? 'Поиск по действию или сотруднику'
                      : 'Поиск в этом разделе'
                  "
                  aria-label="Поиск в разделе" /></label
              ><label v-if="!['history', 'accounts'].includes(section)"
                ><span class="sr-only">Статус записей</span
                ><select v-model="status" aria-label="Статус записей">
                  <option value="all">Все статусы</option>
                  <template v-if="section === 'resorts'"
                    ><option value="published">Опубликован</option>
                    <option value="draft">Черновик</option>
                    <option value="archived">В архиве</option></template
                  ><template v-else-if="section === 'bookings'"
                    ><option value="confirmed">Подтверждена</option>
                    <option value="cancelled">Отменена</option></template
                  ><template v-else
                    ><option value="active">Активен</option>
                    <option
                      :value="section === 'rooms' ? 'maintenance' : 'disabled'"
                    >
                      {{ section === "rooms" ? "На обслуживании" : "Отключён" }}
                    </option></template
                  >
                </select></label
              ><button
                class="text-button"
                @click="load"
                aria-label="Обновить данные"
              >
                ↻ Обновить
              </button>
            </div>
            <div
              v-if="section === 'resorts' && filteredResorts.length"
              class="table-scroll"
              tabindex="0"
              role="region"
              aria-label="Таблица данных"
            >
              <table>
                <thead>
                  <tr>
                    <th>Санаторий</th>
                    <th>Местоположение</th>
                    <th>Номера</th>
                    <th>Статус</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in filteredResorts" :key="r.id">
                    <td>
                      <div class="property-cell">
                        <img
                          src="/assets/resort.jpg"
                          alt="Иллюстрация курорта"
                        />
                        <div>
                          <strong>{{ r.name }}</strong
                          ><small>{{
                            r.subtitle || "Описание ещё не добавлено"
                          }}</small>
                        </div>
                      </div>
                    </td>
                    <td>
                      {{ r.city }}<small>{{ r.address }}</small>
                    </td>
                    <td>
                      <button class="text-button" @click="switchResort(r.id)">
                        {{
                          catalog.rooms.filter((x) => x.resortId === r.id)
                            .length
                        }}
                        комнат →
                      </button>
                    </td>
                    <td>
                      <span :class="['status-pill', r.status]">{{
                        statusNames[r.status]
                      }}</span>
                    </td>
                    <td>
                      <div class="row-actions">
                        <button
                          v-if="r.status !== 'archived'"
                          class="text-button"
                          @click="open('resorts', r)"
                        >
                          Настроить</button
                        ><button
                          v-if="session.isAdmin && r.status !== 'archived'"
                          class="text-button danger"
                          @click="
                            confirm = {
                              kind: 'resorts',
                              item: r,
                              title: 'Архивировать санаторий?',
                              text: 'Санаторий исчезнет с сайта. Записи и история сохранятся.',
                            }
                          "
                        >
                          В архив
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div
              v-else-if="section === 'rooms' && filteredRooms.length"
              class="table-scroll"
              tabindex="0"
              role="region"
              aria-label="Таблица данных"
            >
              <table>
                <thead>
                  <tr>
                    <th>Комната</th>
                    <th>Категория</th>
                    <th>Вместимость</th>
                    <th>За ночь</th>
                    <th>Статус</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in filteredRooms" :key="r.id">
                    <td>
                      <strong>№ {{ r.number }}</strong
                      ><small>{{ r.area }} м²</small>
                    </td>
                    <td>
                      {{ r.title }}<small>{{ r.beds }}</small>
                    </td>
                    <td>{{ r.capacity }} гостя</td>
                    <td class="numeric">{{ money(r.price) }}</td>
                    <td>
                      <span :class="['status-pill', r.status]">{{
                        statusNames[r.status]
                      }}</span>
                    </td>
                    <td>
                      <div class="row-actions">
                        <button class="text-button" @click="open('rooms', r)">
                          Изменить</button
                        ><button
                          class="text-button danger"
                          @click="
                            confirm = {
                              kind: 'rooms',
                              item: r,
                              title: 'Удалить комнату № ' + r.number + '?',
                              text: 'Удаление возможно, только если комната не связана с бронированиями. Иначе используйте статус «На обслуживании».',
                            }
                          "
                        >
                          Удалить
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div
              v-else-if="section === 'tariffs' && filteredTariffs.length"
              class="table-scroll"
              tabindex="0"
              role="region"
              aria-label="Таблица данных"
            >
              <table>
                <thead>
                  <tr>
                    <th>Тариф</th>
                    <th>Что включено</th>
                    <th>Доплата / гость / ночь</th>
                    <th>Статус</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="t in filteredTariffs" :key="t.id">
                    <td>
                      <strong>{{ t.name }}</strong
                      ><small>{{ t.description }}</small>
                    </td>
                    <td>{{ t.features.join(" · ") || "—" }}</td>
                    <td class="numeric">{{ money(t.supplement) }}</td>
                    <td>
                      <span :class="['status-pill', t.status]">{{
                        statusNames[t.status]
                      }}</span>
                    </td>
                    <td>
                      <div class="row-actions">
                        <button class="text-button" @click="open('tariffs', t)">
                          Изменить</button
                        ><button
                          class="text-button danger"
                          @click="
                            confirm = {
                              kind: 'tariffs',
                              item: t,
                              title: 'Удалить тариф «' + t.name + '»?',
                              text: 'Тариф с историей бронирований можно только отключить.',
                            }
                          "
                        >
                          Удалить
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div
              v-else-if="section === 'bookings' && filteredBookings.length"
              class="table-scroll"
              tabindex="0"
              role="region"
              aria-label="Таблица данных"
            >
              <table>
                <thead>
                  <tr>
                    <th>Бронь / гость</th>
                    <th>Номер и тариф</th>
                    <th>Даты</th>
                    <th>Сумма</th>
                    <th>Статус</th>
                    <th>Действие</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="b in filteredBookings" :key="b.id">
                    <td>
                      <strong>{{ b.guestLabel }}</strong
                      ><small
                        >#{{ b.id.slice(0, 8) }} ·
                        {{
                          b.source === "staff" ? "Вручную" : "С сайта"
                        }}</small
                      >
                    </td>
                    <td>
                      № {{ b.unit }} · {{ b.roomName
                      }}<small>{{ b.tariffName }} · {{ b.guests }} гостя</small>
                    </td>
                    <td>
                      {{ dateLabel(b.start)
                      }}<small>до {{ dateLabel(b.end) }}</small>
                    </td>
                    <td class="numeric">{{ money(b.total) }}</td>
                    <td>
                      <span :class="['status-pill', b.status]">{{
                        statusNames[b.status]
                      }}</span>
                    </td>
                    <td>
                      <button
                        v-if="b.status === 'confirmed'"
                        class="text-button danger"
                        @click="
                          confirm = {
                            kind: 'bookings',
                            item: b,
                            title: 'Отменить бронирование?',
                            text: 'Номер освободится на эти даты. Отменённая бронь останется в истории.',
                          }
                        "
                      >
                        Отменить</button
                      ><span v-else>—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div
              v-else-if="section === 'accounts' && filteredAccounts.length"
              class="table-scroll"
              tabindex="0"
              role="region"
              aria-label="Таблица данных"
            >
              <table>
                <thead>
                  <tr>
                    <th>Управляющий</th>
                    <th>Санаторий</th>
                    <th>Доступ</th>
                    <th>Действие</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="a in filteredAccounts" :key="a.id">
                    <td>
                      <strong>{{ a.name }}</strong
                      ><small>{{ a.login }}</small>
                    </td>
                    <td>
                      {{
                        catalog.resorts.find((r) => r.id === a.resortId)
                          ?.name || "—"
                      }}
                    </td>
                    <td>
                      <span :class="['status-pill', a.status]">{{
                        statusNames[a.status]
                      }}</span>
                    </td>
                    <td>
                      <button class="text-button" @click="open('accounts', a)">
                        Настроить доступ
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div
              v-else-if="section === 'history' && filteredAudit.length"
              class="audit-list"
            >
              <details v-for="entry in filteredAudit" :key="entry.id">
                <summary>
                  <span :class="['audit-dot', entry.action]">{{
                    {
                      create: "+",
                      update: "↗",
                      delete: "−",
                      archive: "□",
                      cancel: "×",
                    }[entry.action]
                  }}</span
                  ><span
                    ><strong
                      >{{
                        {
                          create: "Создание",
                          update: "Изменение",
                          delete: "Удаление",
                          archive: "Архивирование",
                          cancel: "Отмена",
                        }[entry.action]
                      }}
                      · {{ entry.label }}</strong
                    ><small
                      >{{ entry.actor }} · {{ timeLabel(entry.at) }} ·
                      Алматы</small
                    ></span
                  ><span class="audit-expand">Детали ↓</span>
                </summary>
                <div class="audit-detail">
                  <table>
                    <thead>
                      <tr>
                        <th>Поле</th>
                        <th>Было</th>
                        <th>Стало</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="change in changes(entry)" :key="change.key">
                        <td>{{ fieldNames[change.key] || change.key }}</td>
                        <td>{{ display(change.before) }}</td>
                        <td>{{ display(change.after) }}</td>
                      </tr>
                    </tbody>
                  </table>
                  <p v-if="!changes(entry).length" class="field-help">
                    Изменений полей нет.
                  </p>
                </div>
              </details>
            </div>
            <div v-else class="work-empty">
              <span>⌕</span>
              <h3>
                {{
                  query || status !== "all"
                    ? "Ничего не найдено"
                    : "Здесь пока нет записей"
                }}
              </h3>
              <p>
                {{
                  query || status !== "all"
                    ? "Измените запрос или сбросьте фильтры."
                    : "Добавьте первую запись, чтобы начать работу."
                }}
              </p>
              <button
                v-if="query || status !== 'all'"
                class="secondary"
                @click="
                  query = '';
                  status = 'all';
                "
              >
                Сбросить фильтры</button
              ><button v-else-if="canAdd" class="primary" @click="open()">
                {{ addLabels[section] }}
              </button>
            </div>
            <div class="table-foot">
              {{
                section === "history"
                  ? "История доступна только для чтения."
                  : "Изменения фиксируются в истории."
              }}
              <span v-if="isDemo">Демонстрационные данные</span>
            </div>
          </section></template
        ></template
      >
    </main></StaffShell
  >
  <ResortEditor
    v-if="editor?.kind === 'resorts'"
    :item="editor.item"
    @close="editor = null"
    @saved="saved"
  />
  <RoomEditor
    v-if="editor?.kind === 'rooms'"
    :item="editor.item"
    :resort-id="selected"
    @close="editor = null"
    @saved="saved"
  />
  <TariffEditor
    v-if="editor?.kind === 'tariffs'"
    :item="editor.item"
    :resort-id="selected"
    @close="editor = null"
    @saved="saved"
  />
  <AccountEditor
    v-if="editor?.kind === 'accounts'"
    :item="editor.item"
    :resorts="catalog.resorts"
    @close="editor = null"
    @saved="saved"
  />
  <BookingEditor
    v-if="editor?.kind === 'bookings' && current"
    staff
    :resort="current"
    :rooms="scopedRooms"
    :tariffs="scopedTariffs"
    @close="editor = null"
    @saved="saved"
  />
  <Modal
    v-if="confirm"
    :title="confirm.title"
    :busy="busy"
    @close="confirm = null"
    ><p class="confirm-text">{{ confirm.text }}</p>
    <p v-if="confirm.error" class="form-error" role="alert">
      {{ confirm.error }}
    </p>
    <div class="form-actions">
      <button class="secondary" :disabled="busy" @click="confirm = null">
        Назад</button
      ><button class="danger-button" :disabled="busy" @click="act">
        {{ busy ? "Сохраняем…" : "Подтвердить" }}
      </button>
    </div></Modal
  >
</template>
