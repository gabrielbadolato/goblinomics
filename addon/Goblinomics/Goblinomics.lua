-- Goblinomics: mostra na dica do item os preços que o site calcula.
-- O jogo não acessa a internet: os dados vêm do Dados.lua desta pasta, que o atualizar.bat baixa do
-- site. O jogo só relê esse arquivo ao entrar com o personagem ou com /reload.

local VERSAO = "1.1"
local D = GoblinomicsDados
local OURO, CINZA, VERDE, VERMELHO = "|cffffd100", "|cff9d9d9d", "|cff40ff40", "|cffff5050"
-- A coleta é de hora em hora; passado isto, quase sempre já existe arquivo mais novo no disco.
local AVISAR_APOS = 75 * 60

local function dizer(texto)
  DEFAULT_CHAT_FRAME:AddMessage(OURO .. "Goblinomics:|r " .. texto)
end

local function moeda(cobre)
  cobre = math.floor(cobre + 0.5)
  local sinal = cobre < 0 and "-" or ""
  cobre = math.abs(cobre)
  -- Com os ícones de moeda do jogo quando o cliente os oferece (a função mudou de lugar entre versões).
  local icones = GetCoinTextureString or (C_CurrencyInfo and C_CurrencyInfo.GetCoinTextureString)
  if icones then
    local ok, texto = pcall(icones, cobre)
    if ok and texto and texto ~= "" then return sinal .. texto end
  end
  local ouro, prata, resto = math.floor(cobre / 10000), math.floor(cobre / 100) % 100, cobre % 100
  local partes = {}
  if ouro > 0 then partes[#partes + 1] = "|cffffd700" .. ouro .. "g|r" end
  if prata > 0 or ouro > 0 then partes[#partes + 1] = "|cffc7c7cf" .. prata .. "s|r" end
  -- Com ouro na conta, o cobre só polui.
  if ouro == 0 then partes[#partes + 1] = "|cffeda55f" .. resto .. "c|r" end
  return sinal .. table.concat(partes, " ")
end

local function idade()
  return D and (time() - D.coletado) or nil
end

local function textoIdade()
  local s = idade()
  if not s then return "sem dados" end
  if s < 0 then s = 0 end
  local min = math.floor(s / 60)
  if min < 60 then return "há " .. min .. " min" end
  local h = math.floor(min / 60)
  if h < 48 then return string.format("há %dh%02d", h, min % 60) end
  return "há " .. math.floor(h / 24) .. " dias"
end

-- ---- Dica do item ----

local function acrescentar(dica, id)
  if not D or not id then return end
  local i = D.itens[id]
  if not i then return end
  dica:AddLine(" ")
  dica:AddDoubleLine(OURO .. "Goblinomics|r", CINZA .. textoIdade() .. "|r")
  if i.m then
    dica:AddDoubleLine("Menor preço", moeda(i.m), 1, 1, 1, 1, 1, 1)
  else
    dica:AddDoubleLine("Menor preço", CINZA .. "nada à venda|r", 1, 1, 1, 1, 1, 1)
  end
  if i.h then
    local variacao = ""
    if i.m and i.h > 0 then
      local pct = math.floor((i.m - i.h) / i.h * 100 + 0.5)
      -- Abaixo da média é bom para quem compra: verde.
      variacao = (pct <= 0 and VERDE or VERMELHO) .. string.format(" (%+d%%)", pct) .. "|r"
    end
    dica:AddDoubleLine("Média de 7 dias", moeda(i.h) .. variacao, 1, 1, 1, 1, 1, 1)
  end
  if i.d then dica:AddDoubleLine("Vendas por dia", string.format("~%.1f", i.d), 1, 1, 1, 1, 1, 1) end
  if i.q then dica:AddDoubleLine("À venda agora", tostring(i.q), 1, 1, 1, 1, 1, 1) end
  if i.c then dica:AddDoubleLine("Custo de fabricar", moeda(i.c), 1, 1, 1, 1, 1, 1) end
  if i.l then
    dica:AddDoubleLine("Lucro de fabricar", (i.l >= 0 and VERDE or VERMELHO) .. moeda(i.l) .. "|r", 1, 1, 1, 1, 1, 1)
  end
  dica:Show()
end

local function idDoLink(link)
  return link and tonumber(string.match(link, "item:(%d+)"))
end

-- Clientes novos entregam o item por TooltipDataProcessor; os antigos, pelo evento OnTooltipSetItem.
if TooltipDataProcessor and TooltipDataProcessor.AddTooltipPostCall and Enum and Enum.TooltipDataType then
  TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, function(dica, dados)
    if dica ~= GameTooltip and dica ~= ItemRefTooltip then return end
    local id = dados and dados.id
    if not id and dica.GetItem then
      local _, link = dica:GetItem()
      id = idDoLink(link)
    end
    acrescentar(dica, id)
  end)
else
  -- Em receitas o evento dispara duas vezes na mesma dica: a marca evita repetir as linhas.
  local feito = {}
  local function ligar(dica)
    if not dica or not dica.HookScript then return end
    dica:HookScript("OnTooltipSetItem", function(self)
      if feito[self] then return end
      local _, link = self:GetItem()
      local id = idDoLink(link)
      if id then
        feito[self] = true
        acrescentar(self, id)
      end
    end)
    dica:HookScript("OnTooltipCleared", function(self) feito[self] = nil end)
  end
  ligar(GameTooltip)
  ligar(ItemRefTooltip)
end

-- ---- Aviso de dados velhos, com botão para recarregar ----

local botao
local dispensado = false
local emTeste = false

local function recarregar()
  if InCombatLockdown and InCombatLockdown() then
    dizer("em combate; recarregue depois com /reload.")
    return
  end
  ReloadUI()
end

local function conferir()
  if not botao then return end
  local s = idade()
  local mostrar = s and s > AVISAR_APOS and not dispensado and GoblinomicsOpcoes.aviso
  if mostrar or emTeste then
    botao:SetText("Goblinomics: preços de " .. textoIdade() .. " - atualizar")
    botao:SetWidth(botao:GetTextWidth() + 30)
    botao:Show()
  else
    botao:Hide()
  end
end

local function criarBotao()
  botao = CreateFrame("Button", "GoblinomicsAviso", UIParent, "UIPanelButtonTemplate")
  botao:SetHeight(22)
  botao:SetPoint("TOP", UIParent, "TOP", 0, -28)
  botao:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  botao:SetScript("OnClick", function(_, tecla)
    if emTeste then
      -- No teste o clique só esconde: recarregar aqui pegaria a pessoa de surpresa.
      emTeste = false
      conferir()
    elseif tecla == "RightButton" then
      dispensado = true
      botao:Hide()
    else
      recarregar()
    end
  end)
  botao:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    GameTooltip:AddLine("Goblinomics")
    GameTooltip:AddLine("Clique: recarrega a interface para ler os preços novos.", 1, 1, 1, true)
    GameTooltip:AddLine("Clique direito: esconde até o próximo carregamento.", 1, 1, 1, true)
    GameTooltip:AddLine("/gob aviso liga ou desliga este botão.", 0.6, 0.6, 0.6, true)
    GameTooltip:Show()
  end)
  botao:SetScript("OnLeave", function() GameTooltip:Hide() end)
  botao:Hide()
end

local quadro = CreateFrame("Frame")
quadro:RegisterEvent("PLAYER_LOGIN")
quadro:SetScript("OnEvent", function()
  if type(GoblinomicsOpcoes) ~= "table" then GoblinomicsOpcoes = {} end
  if GoblinomicsOpcoes.aviso == nil then GoblinomicsOpcoes.aviso = true end
  if not D then
    dizer("sem dados. Rode o atualizar.bat da pasta do addon e depois /reload.")
    return
  end
  dizer(string.format("%d itens de %s, coletados %s. /gob para ajuda.", D.n or 0, D.casa or "?", textoIdade()))
  criarBotao()
  conferir()
  if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(60, conferir) end
end)

SLASH_GOBLINOMICS1 = "/gob"
SLASH_GOBLINOMICS2 = "/goblinomics"
SlashCmdList["GOBLINOMICS"] = function(texto)
  texto = string.lower(texto or "")
  if texto == "aviso" then
    GoblinomicsOpcoes.aviso = not GoblinomicsOpcoes.aviso
    dispensado = false
    dizer("botão de atualizar " .. (GoblinomicsOpcoes.aviso and "ligado." or "desligado."))
    conferir()
  elseif texto == "atualizar" or texto == "reload" then
    recarregar()
  elseif texto == "teste" then
    if not botao then
      dizer("sem dados carregados, não há botão para mostrar.")
    else
      emTeste = true
      conferir()
      dizer("o botão está no alto da tela, no centro. Neste teste, clicar nele só o esconde.")
    end
  else
    if D then
      dizer(string.format("versão %s. %d itens de %s, coletados %s.", VERSAO, D.n or 0, D.casa or "?", textoIdade()))
    else
      dizer("sem dados. Rode o atualizar.bat e depois /reload.")
    end
    dizer("/gob atualizar - recarrega a interface para ler os preços novos")
    dizer("/gob teste - mostra o botão agora, para ver onde ele fica")
    dizer("/gob aviso - liga ou desliga o botão que aparece quando os preços passam de 1h15")
  end
end
