$ErrorActionPreference = 'Stop'

if (-not (Get-Command stripe -ErrorAction SilentlyContinue)) {
    throw 'Stripe CLI não encontrado. Instale-o e execute stripe login antes de continuar.'
}

$secretSecure = Read-Host 'Cole sua chave de teste Stripe (sk_test_)' -AsSecureString
$secretPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secretSecure)
try { $secret = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPtr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPtr) }
if ($secret -notmatch '^sk_test_') { throw 'Use uma chave de teste começando com sk_test_.' }

$env:STRIPE_SECRET_KEY = $secret
$env:APP_BASE_URL = 'http://127.0.0.1:5000'

Write-Host 'Em outra janela, execute: stripe listen --forward-to localhost:5000/api/stripe/webhook'
$webhookSecure = Read-Host 'Cole o segredo exibido pelo Stripe CLI (whsec_)' -AsSecureString
$webhookPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($webhookSecure)
try { $webhookSecret = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($webhookPtr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($webhookPtr) }
if ($webhookSecret -notmatch '^whsec_') { throw 'Segredo de webhook inválido.' }
$env:STRIPE_WEBHOOK_SECRET = $webhookSecret

python app.py
