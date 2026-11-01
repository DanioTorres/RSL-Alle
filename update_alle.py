import io, json, os, time, datetime
import numpy as np
import pandas as pd, requests, yfinance as yf

TAGE = 20  # abrufbare Stichtage
OUT = "data_alle"
UA = {"User-Agent": "Mozilla/5.0 rsl-dashboard"}
SEC = {"Health Care": "Healthcare", "Information Technology": "Technology"}
URL_SP = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
URL_NDX = "https://en.wikipedia.org/wiki/Nasdaq-100"
URL_DOW = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
URL_DAX = "https://en.wikipedia.org/wiki/DAX"
# Eingebaute Reserveliste (Stand 2025) - nur falls Wikipedia nicht lesbar ist und keine listen/dow.csv existiert
DOW = "AAPL AMGN AMZN AXP BA CAT CRM CSCO CVX DIS GS HD HON IBM JNJ JPM KO MCD MMM MRK MSFT NKE NVDA PG SHW TRV UNH V VZ WMT".split()
KRYPTO = "BTC ETH BNB SOL XRP ADA DOGE AVAX TRX LINK DOT LTC BCH XLM ATOM ETC".split()
ORDER = ["S&P 500", "NASDAQ 100", "Dow Jones", "DAX", "STOXX 600", "Russell 2000", "SSE Comp.", "Krypto"]
FILES = {"S&P 500": "listen/sp500.csv", "NASDAQ 100": "listen/nasdaq100.csv", "Dow Jones": "listen/dow.csv", "DAX": "listen/dax.csv",
         "STOXX 600": "listen/stoxx600.csv", "Russell 2000": "listen/russell2000.csv", "SSE Comp.": "listen/sse.csv"}

def pick(cols, *keys):
    for k in keys:
        for c in cols:
            if k in str(c).lower():
                return c
    return None

def parse_table(t, minrows):
    t = t.copy()
    t.columns = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in t.columns]
    cols = list(t.columns)
    tk, nm = pick(cols, "ticker", "symbol"), pick(cols, "company", "security", "name")
    sc = pick(cols, "gics sector", "sector", "industry group", "industry")
    if tk is None or len(t) < minrows:
        return None
    return [(str(a).strip(), str(b).strip() if nm else str(a), str(c).strip() if sc else "Sonstige")
            for a, b, c in zip(t[tk], t[nm] if nm else t[tk], t[sc] if sc else ["Sonstige"] * len(t))]

def wiki(url, minrows):
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    for t in pd.read_html(io.StringIO(r.text)):
        res = parse_table(t, minrows)
        if res:
            return res
    raise ValueError("keine passende Tabelle")

def custom(path):
    df = pd.read_csv(path, sep=None, engine="python", dtype=str, encoding="utf-8-sig").fillna("")
    c = list(df.columns)
    return [(str(r[c[0]]).strip(), str(r[c[1]]).strip() if len(c) > 1 else str(r[c[0]]),
             str(r[c[2]]).strip() if len(c) > 2 else "Sonstige") for _, r in df.iterrows() if str(r[c[0]]).strip()]

def nasdaq_api():
    r = requests.get("https://api.nasdaq.com/api/quote/list-type/nasdaq100", headers={**UA, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    rows = r.json()["data"]["data"]["rows"]
    return [(x["symbol"], x.get("companyName", x["symbol"]), "Sonstige") for x in rows]

def src_sp():
    return wiki(URL_SP, 400)

def src_ndx():
    try:
        return wiki(URL_NDX, 90)
    except Exception as e:
        print("NASDAQ 100 Wikipedia:", e, "-> versuche Nasdaq-API")
    return nasdaq_api()

def src_dow():
    try:
        return wiki(URL_DOW, 28)
    except Exception as e:
        print("Dow Wikipedia:", e, "-> eingebaute Liste (Stand 2025)")
    return [(t, t, "Sonstige") for t in DOW]

def src_dax():
    return wiki(URL_DAX, 35)

AUTO = {"S&P 500": (src_sp, "us"), "NASDAQ 100": (src_ndx, "us"), "Dow Jones": (src_dow, "us"), "DAX": (src_dax, "de")}

def collect():
    info = {}  # ticker -> {"n","sec","ix"}
    def add(index, items, mode):
        for tk, n, sec in items:
            tk = tk.strip().split()[0] if tk.strip() else ""
            if not tk:
                continue
            if mode == "us":
                tk = tk.replace(".", "-")
            elif mode == "de" and "." not in tk:
                tk += ".DE"
            tk = tk.upper()
            d = info.setdefault(tk, {"n": n, "sec": SEC.get(sec, sec) or "Sonstige", "ix": []})
            if index not in d["ix"]:
                d["ix"].append(index)
    for index in ORDER:
        if index == "Krypto":
            continue
        path = FILES[index]
        try:
            if os.path.exists(path):
                add(index, custom(path), "raw")
                print(index, "ok (aus", path + ")")
            elif index in AUTO:
                fn, mode = AUTO[index]
                add(index, fn(), mode)
                print(index, "ok")
            else:
                print(index, "uebersprungen (keine", path + ")")
        except Exception as e:
            print("FEHLER", index, e)
    add("Krypto", [(c + "-USD", c, "Krypto") for c in KRYPTO], "raw")
    return info

def download(chunk):
    for _ in range(3):
        try:
            df = yf.download(chunk, period="2y", interval="1d", auto_adjust=False, progress=False, threads=True)["Close"]
            if isinstance(df, pd.Series):
                df = df.to_frame(chunk[0])
            return df
        except Exception as e:
            print("Retry:", e)
            time.sleep(5)
    return None

def takeover_flags(ret, d):
    w = ret.loc[:d].tail(120)
    arr = w.to_numpy(dtype=float)
    out = {}
    filled = np.where(np.isnan(arr), -1e9, arr)
    for j in np.where(filled.max(axis=0) >= 10)[0]:
        col = filled[:, j]
        k = int(np.argmax(col))
        after = arr[k + 1:, j][-20:]
        after = after[~np.isnan(after)]
        if len(after) >= 5 and np.std(after) < 0.4:
            out[w.columns[j]] = [round(float(col[k]), 1), w.index[k].strftime("%Y-%m-%d"), round(float(np.std(after)), 2)]
    return out

def main():
    info = collect()
    tickers = list(info)
    print(len(tickers), "Ticker")
    frames = [f for f in (download(tickers[i:i + 100]) for i in range(0, len(tickers), 100)) if f is not None]
    px = pd.concat(frames, axis=1)
    px = px.loc[:, ~px.columns.duplicated()]
    px.index = pd.to_datetime(px.index).tz_localize(None)
    now = datetime.datetime.utcnow()
    if now.weekday() < 5 and now.hour * 60 + now.minute < 21 * 60 + 15:
        px = px[px.index < pd.Timestamp(now.date())]
    px = px[px.notna().sum(axis=1) >= 300]
    days = list(px.index[-TAGE:])
    ret = px.pct_change(fill_method=None) * 100
    os.makedirs(OUT, exist_ok=True)
    for old in os.listdir(OUT):
        os.remove(os.path.join(OUT, old))
    names = []
    for d in days:
        sub = px[px.index <= d]
        weekly = sub.resample("W-FRI").last().tail(26)
        sma = weekly.mean()
        ok = (weekly.notna().sum() == 26) & sub.tail(5).notna().any()
        last26 = sub.tail(26)
        sma26 = last26.mean()
        ok26 = last26.notna().sum() >= 20
        filled = sub.ffill()
        close = filled.iloc[-1]
        perf = {k: ((close / filled.iloc[-1 - n] - 1) * 100 if len(filled) > n else None) for k, n in (("d1", 1), ("w1", 5), ("m1", 21))}
        flags = takeover_flags(ret, d)
        rows = []
        for tk in px.columns:
            if tk not in info or not ok.get(tk, False) or not pd.notna(close[tk]):
                continue
            row = {"tk": tk, "n": info[tk]["n"], "sec": info[tk]["sec"], "ix": info[tk]["ix"],
                   "cl": round(float(close[tk]), 2), "sma": round(float(sma[tk]), 2)}
            if ok26.get(tk, False) and pd.notna(sma26[tk]):
                row["s26"] = round(float(sma26[tk]), 2)
            for k, ser in perf.items():
                if ser is not None and pd.notna(ser[tk]):
                    row[k] = round(float(ser[tk]), 2)
            if tk in flags:
                row["ue"] = flags[tk]
            rows.append(row)
        if len(rows) < 300:
            print("Zu wenige Aktien am", d.date())
            continue
        name = d.strftime("%Y-%m-%d")
        with open(f"{OUT}/{name}.json", "w", encoding="utf-8") as f:
            json.dump({"updated": "Handelsschluss " + d.strftime("%d.%m.%Y"), "rows": rows}, f, ensure_ascii=False, separators=(",", ":"))
        names.append(name)
    if not names:
        raise SystemExit("Keine Daten erzeugt")
    with open(f"{OUT}/index.json", "w", encoding="utf-8") as f:
        json.dump({"dates": names[::-1]}, f)
    print(len(names), "Stichtage, neuester:", names[-1])

if __name__ == "__main__":
    main()
