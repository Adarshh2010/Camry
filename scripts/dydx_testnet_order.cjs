#!/usr/bin/env node

const {
  BECH32_PREFIX,
  CompositeClient,
  LocalWallet,
  Network,
  OrderExecution,
  OrderSide,
  OrderTimeInForce,
  OrderType,
  SubaccountInfo,
  utils,
} = require("@dydxprotocol/v4-client-js");

const MAX_CLIENT_ID = 2_147_483_647;

function jsonReplacer(_key, value) {
  return typeof value === "bigint" ? value.toString() : value;
}

function readRequest() {
  const raw = process.argv[2];
  if (!raw) {
    throw new Error("Missing JSON request argument.");
  }
  return JSON.parse(raw);
}

function requireValue(value, name) {
  if (value === undefined || value === null || value === "") {
    throw new Error(`${name} is required.`);
  }
  return value;
}

async function main() {
  const input = readRequest();
  const mnemonic = requireValue(process.env.DYDX_TEST_MNEMONIC, "DYDX_TEST_MNEMONIC");
  const subaccountNumber = Number(process.env.DYDX_SUBACCOUNT_NUMBER || "0");
  const side = input.side === "BUY" ? OrderSide.BUY : OrderSide.SELL;
  const reduceOnly = Boolean(input.reduce_only);
  const symbol = input.symbol || "BTC-USD";
  const price = Number(requireValue(input.price, "price"));
  const size = Number(requireValue(input.size, "size"));

  const wallet = await LocalWallet.fromMnemonic(mnemonic, BECH32_PREFIX);
  const client = await CompositeClient.connect(Network.testnet());
  const subaccount = SubaccountInfo.forLocalWallet(wallet, subaccountNumber);
  const clientId = input.client_id || utils.randomInt(MAX_CLIENT_ID);
  const tx = await client.placeOrder(
    subaccount,
    symbol,
    OrderType.MARKET,
    side,
    price,
    size,
    clientId,
    OrderTimeInForce.IOC,
    0,
    OrderExecution.IOC,
    false,
    reduceOnly,
  );

  console.log(
    JSON.stringify(
      {
        order_id: String(clientId),
        tx_hash: tx?.hash || tx?.transactionHash || tx,
        symbol,
        side: input.side,
        size: String(size),
        price: String(price),
        reduce_only: reduceOnly,
        wallet_address: wallet.address,
        raw: tx,
      },
      jsonReplacer,
    ),
  );
}

main().catch((error) => {
  console.error(JSON.stringify({ error: error.message || String(error) }));
  process.exit(1);
});
