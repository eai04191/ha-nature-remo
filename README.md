# ha-nature-remo

Nature Remoのエアコンと、Remo本体の温度・湿度センサーをHome Assistantで扱うカスタム連携です。Nature Remo Cloud APIを60秒ごとにポーリングします。

[NaNaLinks/homeassistant_nature_remo](https://github.com/NaNaLinks/homeassistant_nature_remo) v0.2.3の置き換えとして作っており、同じドメイン（`nature_remo`）・config entry・unique_idを使うため、既存の設定とentityをそのまま引き継げます。

## できること

- エアコン（climate）
  - 運転モード（冷房・除湿・暖房・送風・自動・OFF）、設定温度、風量、上下風向
  - 選べるモード・温度・風量・風向は、Nature APIが返す機種ごとの範囲（`aircon.range.modes`）から決めます。温度設定のないモード（除湿・送風など）や、風向を選べない機種では、その操作を出しません
  - 室温・湿度は、エアコンを操作するRemo本体のセンサー値を使います
- Remo本体の温度・湿度センサー（sensor）

照明、テレビなどの赤外線リモコン（remote）、スマートメーター（Remo E）、照度・人感センサー、外部センサーの設定（オプション）、`nature_remo.send_light_mode`サービスはありません。

## 必要なもの

- Home Assistant 2026.10.0以降
- Nature Remoのアクセストークン（[home.nature.global](https://home.nature.global/)で発行）

Nature APIには1アカウントあたり5分で30リクエストの制限があります。この連携は定期更新で5分あたり10リクエスト、エアコンの操作1回ごとに最大3リクエスト（操作と直後の再取得。再取得は10秒以内の連続操作ではまとめられます）を使います。同じアカウントのトークンを他のツールでも使う場合は合計に注意してください。

## インストール

### HACS

1. HACSの「カスタムリポジトリ」に`https://github.com/eai04191/ha-nature-remo`を種類「Integration」で追加します
2. 「Nature Remo」をダウンロードし、Home Assistantを再起動します
3. 設定 > デバイスとサービス > 連携を追加 から「Nature Remo」を選び、アクセストークンを入力します

### 手動

`custom_components/nature_remo`を、Home Assistantの設定ディレクトリの`custom_components/nature_remo`にコピーして再起動し、上の手順3を行います。

## 既存連携（NaNaLinks/homeassistant_nature_remo）からの移行

config entry（`data`の`api_key`）、climateとsensorのunique_id、Remo本体のデバイスをそのまま使うため、連携の追加し直しやentity_idの変更は不要です。

1. Home Assistantのバックアップを取ります
2. HACSで既存の「Nature Remo」（NaNaLinks/homeassistant_nature_remo）を削除します。連携が設定済みである旨の確認が出たら「無視」を選んで削除を続けます。HACSの削除は`custom_components/nature_remo`のファイルを消すだけです。設定 > デバイスとサービス にある「Nature Remo」の連携エントリは削除しません（削除するとentityの設定やentity_idの引き継ぎができなくなります）
3. 上の「インストール」の手順1・2でこのリポジトリを入れ、Home Assistantを再起動します
4. 「Nature Remo」の連携がそのまま読み込まれ、エアコンと温度・湿度センサーが同じentity_idで動くことを確認します
5. この連携で作らないentity（照明、リモコン、照度・人感センサー、スマートメーターなど）は「提供されていません」になります。使っていなければentityの設定から削除します

既存連携のオプション（更新間隔、外部センサー）は使いません。更新間隔は60秒固定です。

## 開発

[uv](https://docs.astral.sh/uv/)で開発環境を作ります。依存はHome Assistant 2026.10.1と、それに対応する`pytest-homeassistant-custom-component` 0.13.372です。

```sh
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

テストはNature APIをモックしており、実際のAPIにはアクセスしません。
