param(
  [string]$API = "http://localhost:8000",
  [string]$KEY = $env:INTERNAL_API_KEY,
  [int]$N = 6
)

if (-not $KEY) { throw "Set -KEY or `$env:INTERNAL_API_KEY first." }

# Known-good lanes & load_ids from your dataset
# (equipment, origin, destination, load_id)
$LANES = @(
  @{ eq="Reefer";   o="Charlotte, NC";       d="Raleigh, NC";         lid="LD1013" },
  @{ eq="Dry Van";  o="New Orleans, LA";     d="Birmingham, AL";      lid="LD1012" },
  @{ eq="Reefer";   o="Los Angeles, CA";     d="Phoenix, AZ";         lid="LD1000" },
  @{ eq="Flatbed";  o="Seattle, WA";         d="Portland, OR";        lid="LD1004" },
  @{ eq="Reefer";   o="Salt Lake City, UT";  d="Boise, ID";           lid="LD1010" },
  @{ eq="Step Deck";o="Cleveland, OH";       d="Columbus, OH";        lid="LD1011" },
  @{ eq="Flatbed";  o="Denver, CO";          d="Las Vegas, NV";       lid="LD1005" },
  @{ eq="Reefer";   o="Chicago, IL";         d="Detroit, MI";         lid="LD1002" },
  @{ eq="Flatbed";  o="Houston, TX";         d="Miami, FL";           lid="LD1003" },
  @{ eq="Dry Van";  o="Boston, MA";          d="Philadelphia, PA";    lid="LD1008" },
  @{ eq="Step Deck";o="Minneapolis, MN";     d="Kansas City, MO";     lid="LD1009" },
  @{ eq="Reefer";   o="San Francisco, CA";   d="Sacramento, CA";      lid="LD1006" },
  @{ eq="Step Deck";o="Tampa, FL";           d="Orlando, FL";         lid="LD1014" },
  @{ eq="Reefer";   o="Dallas, TX";          d="Atlanta, GA";         lid="LD1001" }
)

for ($i=1; $i -le $N; $i++) {
  $lane = $LANES[($i-1) % $LANES.Count]
  $mc = (Get-Random -Minimum 140000 -Maximum 199999).ToString()
  $load_id = $lane.lid

  Write-Host "=== Call #$i  MC:$mc  $($lane.eq)  $($lane.o) -> $($lane.d)  (load_id=$load_id) ==="

  # 1) verify MC
  $verifyBody = @{ mc_number = "$mc" } | ConvertTo-Json
  Invoke-RestMethod -Method POST -Uri "$API/verify-mc" -Headers @{ "X-API-Key"=$KEY } -ContentType "application/json" -Body $verifyBody | Out-Null

  # 2) suggest-loads (optional; for visibility only)
  $suggestBody = @{ equipment_type=$lane.eq; origin=$lane.o; destination=$lane.d } | ConvertTo-Json
  try {
    $s = Invoke-RestMethod -Method POST -Uri "$API/suggest-loads" -Headers @{ "X-API-Key"=$KEY } -ContentType "application/json" -Body $suggestBody
    $cnt = ($s.count | ForEach-Object { $_ }); if ($cnt -eq $null) { $cnt = 0 }
    Write-Host "suggest-loads count=$cnt"
  } catch { Write-Host "suggest-loads failed (ok to ignore)" }

  # 3) negotiate: offer a tad high to trigger counter; then accept counter (or accept immediately)
  $firstOffer = 1600
  $nBody1 = @{ load_id=$load_id; mc_number="$mc"; carrier_offer=[double]$firstOffer } | ConvertTo-Json
  $n1 = Invoke-RestMethod -Method POST -Uri "$API/negotiate-round" -Headers @{ "X-API-Key"=$KEY } -ContentType "application/json" -Body $nBody1
  $status = $n1.status; if (-not $status) { $status = $n1.result.status }
  $counter = $n1.broker_counter_offer; if (-not $counter) { $counter = $n1.result.broker_counter_offer }
  $agreed  = $n1.agreed_rate; if (-not $agreed) { $agreed = $n1.result.agreed_rate }
  Write-Host "Round1 → status=$status  counter=$counter  agreed=$agreed"

  if ($status -eq "ongoing" -and $counter) {
    $nBody2 = @{ load_id=$load_id; mc_number="$mc"; carrier_offer=[double]$counter } | ConvertTo-Json
    $n2 = Invoke-RestMethod -Method POST -Uri "$API/negotiate-round" -Headers @{ "X-API-Key"=$KEY } -ContentType "application/json" -Body $nBody2
    $agreed = $n2.agreed_rate; if (-not $agreed) { $agreed = $n2.result.agreed_rate }
    $status = $n2.status;      if (-not $status) { $status = $n2.result.status }
    Write-Host "Confirm → status=$status  agreed=$agreed"
  }

  if (-not $agreed) { $agreed = $firstOffer }

  # 4) summary webhook (non-mutating) + transcript w/ sentiment
  $transcript = @(
    @{ role="event";     content="user_joined" },
    @{ role="assistant"; content="Welcome to SwiftHaul..." },
    @{ role="user";      content="My MC is $mc." },
    @{ role="event";     name="sentiment_hr"; content="neutral_tag" },
    @{ role="assistant"; content="Found load $load_id." },
    @{ role="user";      content="I'll do $agreed." },
    @{ role="event";     name="sentiment_hr"; content="positive_tag" },
    @{ role="assistant"; content="Confirmed at $agreed. Transferring you now." },
    @{ role="event";     content="agent_hung_up" }
  )

  $summaryBody = @{
    mc_number   = "$mc"
    load_id     = $load_id
    agreed_rate = [double]$agreed
    transcript  = $transcript
  } | ConvertTo-Json -Depth 6

  Invoke-RestMethod -Method POST -Uri "$API/webhooks/happyrobot/call-summary" -Headers @{ "X-API-Key"=$KEY } -ContentType "application/json" -Body $summaryBody | Out-Null

  Start-Sleep -Milliseconds 250
}

Write-Host "✅ Done. Refresh http://localhost:8501/"
