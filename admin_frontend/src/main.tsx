import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Boxes,
  BarChart3,
  Check,
  ClipboardList,
  Database,
  Link as LinkIcon,
  LogOut,
  Moon,
  Package,
  RefreshCw,
  Save,
  Settings,
  Sun,
  Trash2,
  Users,
} from 'lucide-react';
import './styles.css';

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

type Stats = {
  users: number;
  orders: number;
  links: number;
};

type BusinessDay = {
  date: string;
  orders_count: number;
  revenue_rub: number;
  issued_links: number;
  price_usd: number;
  cost_per_link_usd: number;
  revenue_usd: number;
  cost_usd: number;
  profit_usd: number;
};

type VisitPoint = {
  visit_date: string;
  visits: number;
};

type ChannelLeavePoint = {
  event_date: string;
  leaves: number;
};

type ChannelLeaveUser = {
  user_id: number;
  username: string;
  first_name: string;
  old_status: string;
  new_status: string;
  created_at: string;
};

type ChannelLeaves = {
  today_leaves: number;
  total_leaves: number;
  chart: ChannelLeavePoint[];
  recent: ChannelLeaveUser[];
};

type Order = {
  id: number;
  user_id: number;
  username: string;
  product_title: string;
  price_rub: number;
  contact: string;
  status: string;
  created_at: string;
};

type StoreUser = {
  id: number;
  username: string;
  first_name: string;
  balance: number;
  language: string;
  ref_code: string;
  created_at: string;
};

type StoreLink = {
  id: number;
  url: string;
  product_code: string;
  purchase_cost_usd: number;
  is_issued: boolean;
  issued_to: number | null;
  created_at: string;
};

type LinksSummary = {
  total: number;
  available: number;
  issued: number;
};

type Product = {
  code: string;
  title: string;
  price_rub: number;
  price_usd: number;
  description: string;
};

type Tab = 'orders' | 'links' | 'product' | 'users';
type UsersSubtab = 'list' | 'leaves';

const PRODUCT_OPTIONS = [
  { code: 'gemini_link_18_month', title: 'Gemini Link 18 months' },
  { code: 'gpt_account_full_warranty', title: 'GPT account full warranty' },
  { code: 'gemini_account_12_month', title: 'Gemini account 12 month' },
];

const ORDER_STATUSES = [
  'Ожидает обработки',
  'Оплачен',
  'Оплачен Crypto Bot, ожидает обработки',
  'Выдан',
  'Выдан автоматически',
  'Резерв, нет в наличии',
  'Отменен',
];

function authHeader(login: string, password: string) {
  return `Basic ${btoa(`${login}:${password}`)}`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

function formatChartDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
  }).format(new Date(value));
}

function App() {
  const [login, setLogin] = useState(localStorage.getItem('admin_login') || 'admin');
  const [password, setPassword] = useState(localStorage.getItem('admin_password') || '');
  const [isAuthed, setIsAuthed] = useState(Boolean(localStorage.getItem('admin_password')));
  const [theme, setTheme] = useState(localStorage.getItem('admin_theme') || 'light');
  const [tab, setTab] = useState<Tab>('orders');
  const [usersSubtab, setUsersSubtab] = useState<UsersSubtab>('list');
  const [linkProductCode, setLinkProductCode] = useState(PRODUCT_OPTIONS[0].code);
  const [productCode, setProductCode] = useState(PRODUCT_OPTIONS[0].code);
  const [stats, setStats] = useState<Stats>({ users: 0, orders: 0, links: 0 });
  const [businessDay, setBusinessDay] = useState<BusinessDay | null>(null);
  const [businessDays, setBusinessDays] = useState<BusinessDay[]>([]);
  const [visits, setVisits] = useState<VisitPoint[]>([]);
  const [channelLeaves, setChannelLeaves] = useState<ChannelLeaves | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [users, setUsers] = useState<StoreUser[]>([]);
  const [links, setLinks] = useState<StoreLink[]>([]);
  const [linksSummary, setLinksSummary] = useState<LinksSummary>({ total: 0, available: 0, issued: 0 });
  const [product, setProduct] = useState<Product | null>(null);
  const [newLinks, setNewLinks] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const headers = useMemo(
    () => ({
      Authorization: authHeader(login, password),
      'Content-Type': 'application/json',
    }),
    [login, password],
  );

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: { ...headers, ...(options.headers || {}) },
    });

    if (!response.ok) {
      throw new Error(response.status === 401 ? 'Неверный логин или пароль' : 'Ошибка запроса');
    }

    return response.json();
  }

  async function loadAll(nextLinkProductCode = linkProductCode, nextProductCode = productCode) {
    setLoading(true);
    setMessage('');
    try {
      const [nextStats, nextBusinessDay, nextBusinessDays, nextVisits, nextChannelLeaves, nextOrders, nextUsers, nextLinks, nextLinksSummary, nextProduct] = await Promise.all([
        request<Stats>('/api/stats'),
        request<BusinessDay>('/api/business/day'),
        request<BusinessDay[]>('/api/business/days?days=30'),
        request<VisitPoint[]>('/api/visits?days=14'),
        request<ChannelLeaves>('/api/channel/leaves?days=14'),
        request<Order[]>('/api/orders'),
        request<StoreUser[]>('/api/users'),
        request<StoreLink[]>(`/api/links?product_code=${encodeURIComponent(nextLinkProductCode)}`),
        request<LinksSummary>(`/api/links/summary?product_code=${encodeURIComponent(nextLinkProductCode)}`),
        request<Product>(`/api/product?code=${encodeURIComponent(nextProductCode)}`),
      ]);
      setStats(nextStats);
      setBusinessDay(nextBusinessDay);
      setBusinessDays(nextBusinessDays);
      setVisits(nextVisits);
      setChannelLeaves(nextChannelLeaves);
      setOrders(nextOrders);
      setUsers(nextUsers);
      setLinks(nextLinks);
      setLinksSummary(nextLinksSummary);
      setProduct(nextProduct);
      localStorage.setItem('admin_login', login);
      localStorage.setItem('admin_password', password);
      setIsAuthed(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось загрузить данные');
      setIsAuthed(false);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (isAuthed) {
      loadAll();
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('admin_theme', theme);
  }, [theme]);

  async function submitLogin(event: React.FormEvent) {
    event.preventDefault();
    await loadAll();
  }

  async function addLinkBatch(event: React.FormEvent) {
    event.preventDefault();
    const result = await request<{ added: number }>('/api/links', {
      method: 'POST',
      body: JSON.stringify({ links: newLinks, product_code: linkProductCode }),
    });
    setNewLinks('');
    setMessage(`Добавлено ссылок: ${result.added}`);
    await loadAll();
  }

  async function saveProduct(event: React.FormEvent) {
    event.preventDefault();
    if (!product) return;
    const saved = await request<Product>('/api/product', {
      method: 'PUT',
      body: JSON.stringify(product),
    });
    setProduct(saved);
    setMessage('Данные товара сохранены');
    await loadAll();
  }

  async function updateStatus(orderId: number, status: string) {
    await request<Order>(`/api/orders/${orderId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
    await loadAll();
  }

  async function deleteLink(linkId: number) {
    if (!window.confirm('Удалить эту ссылку?')) return;
    await request<{ deleted: number }>(`/api/links/${linkId}`, {
      method: 'DELETE',
    });
    setMessage('Ссылка удалена');
    await loadAll();
  }

  async function clearAvailableLinks() {
    if (!window.confirm('Удалить все ссылки, которые еще не выданы?')) return;
    const result = await request<{ deleted: number }>(`/api/links/available?product_code=${encodeURIComponent(linkProductCode)}`, {
      method: 'DELETE',
    });
    setMessage(`Удалено невыданных ссылок: ${result.deleted}`);
    await loadAll();
  }

  function logout() {
    localStorage.removeItem('admin_password');
    setPassword('');
    setIsAuthed(false);
  }

  function toggleTheme() {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  }

  const maxVisits = Math.max(...visits.map((point) => point.visits), 1);
  const maxLeaves = Math.max(...(channelLeaves?.chart.map((point) => point.leaves) || []), 1);

  if (!isAuthed) {
    return (
      <main className="login-screen">
        <form className="login-panel" onSubmit={submitLogin}>
          <Database size={32} />
          <h1>Админка магазина</h1>
          <label>
            Логин
            <input value={login} onChange={(event) => setLogin(event.target.value)} />
          </label>
          <label>
            Пароль
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button type="submit" disabled={loading}>
            <Check size={18} />
            Войти
          </button>
          {message && <p className="message error">{message}</p>}
        </form>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>Gemini Store</h1>
          <p>Управление товаром, ссылками и заказами</p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="ghost"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Включить светлую тему' : 'Включить темную тему'}
            title={theme === 'dark' ? 'Светлая тема' : 'Темная тема'}
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button type="button" className="ghost" onClick={loadAll} disabled={loading}>
            <RefreshCw size={18} />
          </button>
          <button type="button" className="ghost" onClick={logout}>
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <section className="stats-grid">
        <div className="stat">
          <Users size={20} />
          <span>Пользователи</span>
          <strong>{stats.users}</strong>
        </div>
        <div className="stat">
          <ClipboardList size={20} />
          <span>Заказы</span>
          <strong>{stats.orders}</strong>
        </div>
        <div className="stat">
          <Boxes size={20} />
          <span>Ссылки</span>
          <strong>{stats.links}</strong>
        </div>
      </section>

      {businessDay && (
        <section className="panel finance-panel">
          <div className="panel-heading">
            <h2>
              <BarChart3 size={20} />
              Финансы за день
            </h2>
            <span className="muted-label">{businessDay.date}</span>
          </div>
          <div className="finance-grid">
            <span>
              Оборот
              <strong>{Number(businessDay.revenue_rub).toFixed(0)} ₽</strong>
            </span>
            <span>
              Заказов
              <strong>{businessDay.orders_count}</strong>
            </span>
            <span>
              Выдано ссылок
              <strong>{businessDay.issued_links}</strong>
            </span>
            <span>
              Прибыль
              <strong>${Number(businessDay.profit_usd).toFixed(2)}</strong>
            </span>
          </div>
          <p className="finance-note">
            Закуп считается по каждой выданной ссылке отдельно. Средний закуп за сегодня: ${Number(businessDay.cost_per_link_usd).toFixed(2)}.
          </p>
        </section>
      )}

      <section className="panel">
        <div className="panel-heading">
          <h2>
            <BarChart3 size={20} />
            Статистика по дням
          </h2>
          <span className="muted-label">последние 30 дней</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Дата</th>
                <th>Заказы</th>
                <th>Оборот</th>
                <th>Выдано</th>
                <th>Выручка $</th>
                <th>Закуп $</th>
                <th>Прибыль $</th>
              </tr>
            </thead>
            <tbody>
              {businessDays.map((day) => (
                <tr key={day.date}>
                  <td>{day.date}</td>
                  <td>{day.orders_count}</td>
                  <td>{Number(day.revenue_rub).toFixed(0)} ₽</td>
                  <td>{day.issued_links}</td>
                  <td>${Number(day.revenue_usd).toFixed(2)}</td>
                  <td>${Number(day.cost_usd).toFixed(2)}</td>
                  <td>
                    <strong>${Number(day.profit_usd).toFixed(2)}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel visits-panel">
        <div className="panel-heading">
          <h2>
            <BarChart3 size={20} />
            Уникальные посещения
          </h2>
          <span className="muted-label">за 14 дней</span>
        </div>
        <div className="visits-chart" aria-label="График уникальных посещений бота по дням">
          {visits.map((point) => (
            <div className="visit-bar" key={point.visit_date}>
              <strong>{point.visits}</strong>
              <div className="bar-track">
                <span style={{ height: `${Math.max((point.visits / maxVisits) * 100, point.visits ? 8 : 0)}%` }} />
              </div>
              <small>{formatChartDate(point.visit_date)}</small>
            </div>
          ))}
        </div>
      </section>

      <nav className="tabs">
        <button className={tab === 'orders' ? 'active' : ''} onClick={() => setTab('orders')}>
          <ClipboardList size={18} />
          Заказы
        </button>
        <button className={tab === 'links' ? 'active' : ''} onClick={() => setTab('links')}>
          <LinkIcon size={18} />
          Ссылки
        </button>
        <button className={tab === 'product' ? 'active' : ''} onClick={() => setTab('product')}>
          <Settings size={18} />
          Товар
        </button>
        <button className={tab === 'users' ? 'active' : ''} onClick={() => setTab('users')}>
          <Users size={18} />
          Пользователи
        </button>
      </nav>

      {message && <p className="message">{message}</p>}

      {tab === 'orders' && (
        <section className="panel">
          <h2>Заказы</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Товар</th>
                  <th>Пользователь</th>
                  <th>Контакт</th>
                  <th>Статус</th>
                  <th>Дата</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr key={order.id}>
                    <td>#{order.id}</td>
                    <td>{order.product_title}</td>
                    <td>
                      {order.username}
                      <small>{order.user_id}</small>
                    </td>
                    <td>{order.contact}</td>
                    <td>
                      <select
                        value={order.status}
                        onChange={(event) => updateStatus(order.id, event.target.value)}
                      >
                        {!ORDER_STATUSES.includes(order.status) && <option>{order.status}</option>}
                        {ORDER_STATUSES.map((status) => (
                          <option key={status}>{status}</option>
                        ))}
                      </select>
                    </td>
                    <td>{formatDate(order.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {tab === 'links' && (
        <section className="split">
          <form className="panel" onSubmit={addLinkBatch}>
            <h2>Добавить товарные позиции</h2>
            <label>
              Категория
              <select
                value={linkProductCode}
                onChange={async (event) => {
                  const nextCode = event.target.value;
                  setLinkProductCode(nextCode);
                  await loadAll(nextCode, productCode);
                }}
              >
                {PRODUCT_OPTIONS.map((option) => (
                  <option value={option.code} key={option.code}>{option.title}</option>
                ))}
              </select>
            </label>
            <label>
              Каждая позиция с новой строки
              <textarea
                value={newLinks}
                onChange={(event) => setNewLinks(event.target.value)}
                placeholder="https://example.com/link-1&#10;email:password:2FA"
              />
            </label>
            <button type="submit">
              <Package size={18} />
              Добавить
            </button>
          </form>
          <section className="panel">
            <div className="panel-heading">
              <h2>Последние позиции</h2>
              <button className="danger" type="button" onClick={clearAvailableLinks}>
                <Trash2 size={18} />
                Очистить невыданные
              </button>
            </div>
            <div className="link-summary">
              <span>
                Всего
                <strong>{linksSummary.total}</strong>
              </span>
              <span>
                В наличии
                <strong>{linksSummary.available}</strong>
              </span>
              <span>
                Выдано
                <strong>{linksSummary.issued}</strong>
              </span>
            </div>
            <div className="link-list">
              {links.map((link) => (
                <div className="link-row" key={link.id}>
                  <span>{link.url}</span>
                  <strong>{link.is_issued ? 'Выдана' : `В наличии · $${Number(link.purchase_cost_usd).toFixed(2)}`}</strong>
                  <button
                    className="danger icon-button"
                    type="button"
                    aria-label="Удалить ссылку"
                    title="Удалить ссылку"
                    onClick={() => deleteLink(link.id)}
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              ))}
            </div>
          </section>
        </section>
      )}

      {tab === 'product' && product && (
        <form className="panel product-form" onSubmit={saveProduct}>
          <h2>Настройки товара</h2>
          <label>
            Категория
            <select
              value={productCode}
              onChange={async (event) => {
                const nextCode = event.target.value;
                setProductCode(nextCode);
                await loadAll(linkProductCode, nextCode);
              }}
            >
              {PRODUCT_OPTIONS.map((option) => (
                <option value={option.code} key={option.code}>{option.title}</option>
              ))}
            </select>
          </label>
          <div className="product-row">
            <label>
              Название
              <input
                value={product.title}
                onChange={(event) => setProduct({ ...product, title: event.target.value })}
              />
            </label>
            <label>
              Цена ₽
              <input
                type="number"
                min="0"
                step="1"
                value={product.price_rub}
                onChange={(event) => setProduct({ ...product, price_rub: Number(event.target.value) })}
              />
            </label>
            <label>
              Цена $
              <input
                type="number"
                min="0"
                step="0.01"
                value={product.price_usd}
                onChange={(event) => setProduct({ ...product, price_usd: Number(event.target.value) })}
              />
            </label>
          </div>
          <label>
            Описание в карточке товара
            <textarea
              value={product.description}
              onChange={(event) => setProduct({ ...product, description: event.target.value })}
            />
          </label>
          <button type="submit">
            <Save size={18} />
            Сохранить
          </button>
        </form>
      )}

      {tab === 'users' && (
        <section className="panel">
          <h2>Пользователи</h2>
          <div className="subtabs">
            <button
              type="button"
              className={usersSubtab === 'list' ? 'active' : ''}
              onClick={() => setUsersSubtab('list')}
            >
              <Users size={18} />
              Пользователи
            </button>
            <button
              type="button"
              className={usersSubtab === 'leaves' ? 'active' : ''}
              onClick={() => setUsersSubtab('leaves')}
            >
              <LogOut size={18} />
              Отписки
            </button>
          </div>
          {usersSubtab === 'list' && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Username</th>
                    <th>Имя</th>
                    <th>Баланс</th>
                    <th>Реф. код</th>
                    <th>Дата</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>{user.id}</td>
                      <td>{user.username || '-'}</td>
                      <td>{user.first_name || '-'}</td>
                      <td>{Number(user.balance).toFixed(0)} ₽</td>
                      <td>{user.ref_code}</td>
                      <td>{formatDate(user.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {usersSubtab === 'leaves' && channelLeaves && (
            <div className="channel-section">
              <div className="panel-heading">
                <h2>
                  <LogOut size={20} />
                  Отписки от канала
                </h2>
                <span className="muted-label">за 14 дней</span>
              </div>
              <div className="channel-summary">
                <span>
                  Сегодня
                  <strong>{channelLeaves.today_leaves}</strong>
                </span>
                <span>
                  Всего
                  <strong>{channelLeaves.total_leaves}</strong>
                </span>
              </div>
              <div className="leaves-chart" aria-label="График отписок от канала по дням">
                {channelLeaves.chart.map((point) => (
                  <div className="visit-bar" key={point.event_date}>
                    <strong>{point.leaves}</strong>
                    <div className="bar-track danger-track">
                      <span style={{ height: `${Math.max((point.leaves / maxLeaves) * 100, point.leaves ? 8 : 0)}%` }} />
                    </div>
                    <small>{formatChartDate(point.event_date)}</small>
                  </div>
                ))}
              </div>
              <div className="table-wrap compact-table">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Username</th>
                      <th>Имя</th>
                      <th>Дата выхода</th>
                    </tr>
                  </thead>
                  <tbody>
                    {channelLeaves.recent.map((user) => (
                      <tr key={`${user.user_id}-${user.created_at}`}>
                        <td>{user.user_id}</td>
                        <td>{user.username || '-'}</td>
                        <td>{user.first_name || '-'}</td>
                        <td>{formatDate(user.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      )}
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
