$ErrorActionPreference = 'Stop'

Write-Output '===== Restart desktop pet ====='
Get-Process -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -like 'C:\Program Files\灵梦桌宠*' } |
  Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Start-Process -FilePath 'C:\Program Files\灵梦桌宠\lingmeng-desktop-pet.exe'
Start-Sleep -Seconds 16

Get-Process -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -like 'C:\Program Files\灵梦桌宠*' } |
  Select-Object Id, ProcessName, StartTime, Path |
  Format-Table -AutoSize

Write-Output '===== Health ====='
$health = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 10
[pscustomobject]@{
  Ok = $health.ok
  Agent = $health.agentProvider + ':' + $health.agentModel
  Tts = $health.ttsConfigured
  DoubaoAsr = $health.doubaoAsrConfigured
  Identity = $health.identityStatus
  RagEmbedding = $health.ragEmbeddingProvider
} | Format-List

Write-Output '===== RAG ====='
$rag = Invoke-RestMethod 'http://127.0.0.1:8000/api/rag/health' -TimeoutSec 10
[pscustomobject]@{
  Ok = $rag.ok
  Store = $rag.store
  CharacterKnowledge = $rag.collections.character_knowledge
  UserDocuments = $rag.collections.user_documents
  Error = $rag.error
} | Format-List

Write-Output '===== Tools ====='
Invoke-RestMethod 'http://127.0.0.1:8000/api/tools' -TimeoutSec 10 |
  Select-Object name, enabled, risk_level, requires_confirmation |
  Format-Table -AutoSize

Write-Output '===== Music control live call: pause ====='
$body = @{
  session_id = 'deployed-feature-check'
  tool_name = 'control_music'
  arguments = @{ action = 'pause' }
} | ConvertTo-Json -Depth 4
Invoke-RestMethod 'http://127.0.0.1:8000/api/tools/execute' -Method Post -ContentType 'application/json; charset=utf-8' -Body $body -TimeoutSec 20 |
  Select-Object status, approval, error_code, error_message, result |
  Format-List

