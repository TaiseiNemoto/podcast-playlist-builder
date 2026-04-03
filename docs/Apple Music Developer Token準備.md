# Apple Music Developer Token 準備

## このドキュメントの目的

[`scripts/search_apple_music.py`](C:/Users/nemoto/Documents/dev/private/podcast-playlist-builder/scripts/search_apple_music.py) を実行するには、Apple Music API 用の `Developer Token` が必要です。

このドキュメントでは、Apple Developer 側で必要な準備をして、最終的に PowerShell の環境変数 `APPLE_MUSIC_DEVELOPER_TOKEN` に設定できる状態までを整理します。

---

## まず理解しておくこと

Apple Music API を使うには、大きく次の 2 つが必要です。

1. Apple Developer 側の設定
2. その設定をもとに署名した `Developer Token`

`Developer Token` は、Apple Developer から直接コピペでもらうものではありません。  
Apple Developer で用意した `Media Identifier` と `Private Key` を使って、自分で JWT を生成して使います。

---

## 今回の用途

今回フェーズ3-1で必要なのは Apple Music の catalog 検索だけです。  
この段階では `Music User Token` は不要で、`Developer Token` だけあれば進められます。

---

## 必要なもの

事前に必要なのは次です。

- Apple Developer Program に参加しているアカウント
- `Account Holder` または `Admin` 権限
- Apple Developer の Certificates, Identifiers & Profiles へ入れること

Apple の公式ヘルプでは、`Media Identifier` と `Private Key` を用意して Developer Token を生成する流れが案内されています。

---

## 手順1: Media Identifier を作成する

Apple Developer の Certificates, Identifiers & Profiles で `Media IDs` を作成します。

やることは次です。

1. `Identifiers` を開く
2. `+` ボタンから `Media IDs` を選ぶ
3. 説明文を入力する
4. reverse-domain 形式の識別子を入力する
5. 必要なサービスを有効にして登録する

補足:

- 説明文は、Apple Music のアクセス許可画面で見えるアプリ名に使われます

---

## 手順2: MusicKit を有効にする

Apple のサービス設定で `MusicKit` を有効にします。

実装上は、Apple Music catalog 取得や後続のユーザー認証に関わる前提設定です。

---

## 手順3: Private Key を作成する

次に `Keys` から Media Services 用の private key を作成します。

やることは次です。

1. `Keys` を開く
2. `+` ボタンで新しい key を作る
3. `Media Services` を有効にする
4. 必要なら `Configure` で対象の media identifier を選ぶ
5. key を作成して `.p8` ファイルをダウンロードする

重要:

- `.p8` ファイルはその場でしかダウンロードできません
- 安全な場所に保管してください

この時に次の値を控えます。

- `Key ID` (`kid`)
- `Team ID`
- `Media Identifier`
- ダウンロードした `.p8` ファイルの中身

---

## 手順4: Developer Token を生成する

ここで自分で JWT を生成します。

Developer Token には、少なくとも次の情報が入ります。

- `alg`: `ES256`
- `kid`: 作成した key の ID
- `iss`: Apple Developer の Team ID
- `iat`: 発行時刻
- `exp`: 有効期限

そして、`.p8` の private key で署名します。

今回のリポジトリでは、まずは生成済みの JWT を環境変数へ入れる運用で十分です。

---

## 手順5: PowerShell に設定する

Developer Token が作れたら、PowerShell で次のように設定します。

```powershell
$env:APPLE_MUSIC_DEVELOPER_TOKEN="ここに生成したJWT"
```

その後、候補検索スクリプトを実行します。

```powershell
python scripts/search_apple_music.py
```

---

## 必要なら今後ファイル化するもの

今は環境変数へ直接入れれば十分ですが、今後必要なら次のように整理できます。

- `.env` に保存する
- `token.json` のようなローカル設定ファイルに保存する
- JWT 生成スクリプトを別途作る

ただし、まずは手動で 1 回動かす方が理解しやすいです。

---

## つまずきやすい点

### 1. Apple Developer で token 自体は発行されない

Apple Developer 上で手に入るのは主に次です。

- Media Identifier
- Private Key
- Key ID

JWT 自体は自分で生成する必要があります。

### 2. `.p8` をなくすと面倒

`.p8` は再ダウンロードできない前提で扱った方が安全です。  
なくした場合は、新しい key を作り直して切り替える運用になります。

### 3. `Music User Token` とは別物

今回使う `Developer Token` は catalog 検索用です。  
将来プレイリストを作る段階では、別途 `Music User Token` が必要です。

---

## 今このリポジトリで必要な値

最低限必要なのは次です。

- `APPLE_MUSIC_DEVELOPER_TOKEN`

将来のプレイリスト追加フェーズでは、さらに次が必要になります。

- `Music User Token`

---

## 参考

Apple 公式の参考ページ:

- [MusicKit | Apple Developer](https://developer.apple.com/musickit/)
- [MusicKit Service Setup](https://developer.apple.com/help/account/services/musickit)
- [Create a media identifier and private key](https://developer.apple.com/help/account/capabilities/create-a-media-identifier-and-private-key/)
- [Create a private key to access a service](https://developer.apple.com/help/account/keys/create-a-private-key/)
- [Search | Apple Music API](https://developer.apple.com/documentation/applemusicapi/search)

必要なら次に、`Developer Token` をローカルで生成するための Python スクリプトも追加できます。
