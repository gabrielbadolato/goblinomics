-- Goblinomics: mostra na dica do item os números que o site calcula e põe um botão no minimapa.
-- O jogo não acessa a internet: os dados vêm do Dados.lua desta pasta, que o atualizar.bat baixa do
-- site. O jogo só relê esse arquivo ao entrar com o personagem ou com /reload.

-- G: a tabela do addon, que o jogo entrega a todos os arquivos dele; é por ela que a Janela.lua usa o que está aqui.
local _, G = ...
G = G or {}
local VERSAO = "1.3"
local D = GoblinomicsDados
local OURO, CINZA, VERDE, VERMELHO, BRANCO = "|cffffd100", "|cff9d9d9d", "|cff40ff40", "|cffff5050", "|cffffffff"
local ICONE = "Interface\\AddOns\\Goblinomics\\Icone"
-- A coleta é de hora em hora; passado isto, quase sempre já existe arquivo mais novo no disco.
local AVISAR_APOS = 75 * 60
-- Abaixo disto em relação à média de 7 dias, e vendendo pelo menos uma por dia, é pechincha.
local PECHINCHA = 0.7

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

-- 35601.4 -> "35.601"; abaixo de 100 mantém uma casa decimal quando pedida.
local function numero(n, decimal)
  if decimal and n < 100 then return (string.gsub(string.format("%.1f", n), "%.", ",")) end
  local texto = tostring(math.floor(n + 0.5))
  local com_pontos = string.gsub(string.reverse(texto), "(%d%d%d)", "%1.")
  return (string.gsub(string.reverse(com_pontos), "^%.", ""))
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

local function resumo()
  if not D then return "sem dados: rode o atualizar.bat e recarregue" end
  return string.format("%d itens de %s, coletados %s", D.n or 0, D.casa or "?", textoIdade())
end

-- ---- Auctionator: o preço do último scan da pessoa, quando ele é de hoje ----

local QUEM_CHAMA = "Goblinomics"

local function precoDoScan(id)
  local api = Auctionator and Auctionator.API and Auctionator.API.v1
  if not api or not api.GetAuctionPriceByItemID then return nil end
  local ok, preco = pcall(api.GetAuctionPriceByItemID, QUEM_CHAMA, id)
  if not ok or type(preco) ~= "number" then return nil end
  local dias
  if api.GetAuctionAgeByItemID then
    local okIdade, idadeEmDias = pcall(api.GetAuctionAgeByItemID, QUEM_CHAMA, id)
    if okIdade then dias = idadeEmDias end
  end
  return preco, dias
end

-- Lucro por unidade de fabricar o item com os preços do scan: venda pelo scan (só se for de hoje) menos a
-- taxa de 5%, materiais pelo scan, pelo NPC quando sai mais barato, ou pelo Goblinomics quando o scan não tem.
local function lucroPeloScan(id)
  local f = D and D.fab and D.fab[id]
  if not f then return nil end
  local venda, dias = precoDoScan(id)
  if not venda or dias ~= 0 then return nil end
  local custo = 0
  for k = 1, #f.m, 2 do
    local material, quantidade = f.m[k], f.m[k + 1]
    local preco = precoDoScan(material)
    local npc = D.npc and D.npc[material]
    if npc and (not preco or npc <= preco) then preco = npc end
    if not preco then preco = D.itens[material] and D.itens[material].m end
    if not preco then return nil end
    custo = custo + preco * quantidade
  end
  return venda * 0.95 - custo / (f.f or 1)
end

-- ---- Dica do item ----

local function par(dica, rotulo, valor)
  dica:AddDoubleLine(rotulo, valor, 1, 1, 1, 1, 1, 1)
end

-- Frase longa: uma linha só, com quebra automática.
local function frase(dica, rotulo, texto)
  dica:AddLine(BRANCO .. rotulo .. ":|r " .. texto, 0.78, 0.78, 0.78, true)
end

local function acrescentar(dica, id)
  if not D or not id then return end
  local i = D.itens[id]
  if not i then return end
  local op = GoblinomicsOpcoes or {}
  if op.dica == false then return end
  dica:AddLine(" ")
  dica:AddDoubleLine(OURO .. "Goblinomics|r", CINZA .. textoIdade() .. "|r")
  if i.m then
    par(dica, "Menor preço", moeda(i.m))
  elseif i.h then
    par(dica, "Menor preço", CINZA .. "nada à venda|r")
  end
  if i.h then
    local variacao = ""
    if i.m and i.h > 0 then
      local pct = math.floor((i.m - i.h) / i.h * 100 + 0.5)
      -- Abaixo da média é bom para quem compra: verde.
      variacao = (pct <= 0 and VERDE or VERMELHO) .. string.format(" (%+d%%)", pct) .. "|r"
    end
    par(dica, "Média de 7 dias", moeda(i.h) .. variacao)
  end
  if i.d then par(dica, "Vendas por dia", "~" .. numero(i.d, true)) end
  if i.q then par(dica, "À venda agora", numero(i.q)) end
  if i.m and i.h and i.d and i.d >= 1 and i.m <= i.h * PECHINCHA then
    dica:AddLine(VERDE .. "Pechincha: bem abaixo da média e com saída|r")
  end
  if i.n then
    dica:AddLine(VERMELHO .. "Vale mais vender ao NPC (" .. moeda(i.n) .. "|r" .. VERMELHO .. ") que no leilão|r")
  end
  -- Material que também dá para fabricar com prejuízo (couro a partir de couro menor, barra, tecido):
  -- custo, lucro e quem faz só enchem a dica; quem quer o material compra ou coleta.
  local soMaterial = i.u and (not i.l or i.l < 0)
  if not soMaterial then
    if i.c then par(dica, "Custo de fabricar", moeda(i.c)) end
    if i.l then par(dica, "Lucro de fabricar", (i.l >= 0 and VERDE or VERMELHO) .. moeda(i.l) .. "|r") end
    local ok, peloScan = pcall(lucroPeloScan, id)
    if ok and peloScan then
      par(dica, "Lucro pelo seu scan de hoje", (peloScan >= 0 and VERDE or VERMELHO) .. moeda(peloScan) .. "|r")
    end
    if i.g then frase(dica, "Quem faz na guilda", i.g) end
  end
  -- Item fabricável: a receita que o ensina, o preço dela e onde consegui-la.
  local receita = i.r and D.itens[i.r]
  if receita then
    if receita.m then par(dica, "Receita no leilão", moeda(receita.m)) end
    if receita.o then frase(dica, "Receita", receita.o) end
  end
  -- O próprio item é uma receita.
  if i.o then frase(dica, "Onde conseguir", i.o) end
  if i.u then
    local lucrativas = i.ul and (", " .. VERDE .. i.ul .. " com lucro agora|r") or ""
    frase(dica, "Usado em", numero(i.u) .. (i.u == 1 and " receita" or " receitas") .. lucrativas)
  end
  if i.z then frase(dica, "Onde coletar", i.z) end
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

-- ---- Recarregar ----

local function recarregar()
  if InCombatLockdown and InCombatLockdown() then
    dizer("em combate; recarregue depois.")
    return
  end
  ReloadUI()
end

-- ---- Aviso de dados velhos, com botão para recarregar ----

local aviso
local dispensado = false
local emTeste = false

local function conferir()
  if not aviso then return end
  local s = idade()
  local mostrar = s and s > AVISAR_APOS and not dispensado and GoblinomicsOpcoes.aviso
  if mostrar or emTeste then
    aviso:SetText("Goblinomics: preços de " .. textoIdade() .. " - atualizar")
    aviso:SetWidth(aviso:GetTextWidth() + 30)
    aviso:Show()
  else
    aviso:Hide()
  end
end

local function criarAviso()
  aviso = CreateFrame("Button", "GoblinomicsAviso", UIParent, "UIPanelButtonTemplate")
  aviso:SetHeight(22)
  aviso:SetPoint("TOP", UIParent, "TOP", 0, -28)
  aviso:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  aviso:SetScript("OnClick", function(_, tecla)
    if emTeste then
      -- No teste o clique só esconde: recarregar aqui pegaria a pessoa de surpresa.
      emTeste = false
      conferir()
    elseif tecla == "RightButton" then
      dispensado = true
      aviso:Hide()
    else
      recarregar()
    end
  end)
  aviso:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    GameTooltip:AddLine("Goblinomics")
    GameTooltip:AddLine("Clique: recarrega a interface para ler os preços novos.", 1, 1, 1, true)
    GameTooltip:AddLine("Clique direito: esconde até o próximo carregamento.", 1, 1, 1, true)
    GameTooltip:Show()
  end)
  aviso:SetScript("OnLeave", function() GameTooltip:Hide() end)
  aviso:Hide()
end

-- ---- Diagnóstico: o que este cliente do jogo oferece, para as próximas funções do addon ----

local function existe(caminho)
  local atual = _G
  for parte in string.gmatch(caminho, "[^.]+") do
    if type(atual) ~= "table" then return false end
    atual = atual[parte]
    if atual == nil then return false end
  end
  return true
end

local SONDAS = {
  {"Dica", {"TooltipDataProcessor", "C_TooltipInfo", "GameTooltip.GetItem", "GetItemInfo", "C_Item.GetItemInfo"}},
  {"Profissão", {"TradeSkillFrame", "ProfessionsFrame", "CraftFrame", "GetNumTradeSkills", "GetTradeSkillInfo",
    "GetTradeSkillItemLink", "C_TradeSkillUI", "C_TradeSkillUI.GetRecipeInfo", "TradeSkillFrame_Update"}},
  {"Bolsas", {"C_Container", "C_Container.GetContainerItemLink", "GetContainerItemLink", "ContainerFrame1", "Baganator", "BagnonFrameinventory"}},
  {"Vendedor", {"MerchantFrame", "GetMerchantItemLink", "GetMerchantItemInfo", "C_MerchantFrame"}},
  {"Leilão", {"AuctionFrame", "AuctionHouseFrame", "C_AuctionHouse", "GetAuctionItemInfo"}},
  {"Mapa", {"GetRealZoneText", "GetZoneText", "C_Map.GetBestMapForUnit", "C_Map.GetMapInfo"}},
  {"Interface", {"BackdropTemplateMixin", "C_Timer.NewTicker", "LibStub", "UIDropDownMenu_Initialize", "MenuUtil",
    "C_AddOns.IsAddOnLoaded", "IsAddOnLoaded", "Settings", "InterfaceOptions_AddCategory", "ScrollUtil", "FauxScrollFrame_Update"}},
  {"Moeda", {"GetCoinTextureString", "C_CurrencyInfo.GetCoinTextureString", "GetMoneyString"}},
  {"Auctionator", {"Auctionator", "Auctionator.API", "Auctionator.API.v1", "AUCTIONATOR_PRICE_DATABASE", "Atr_GetAuctionBuyout"}},
}

local function diagnostico()
  local linhas = {}
  local versao, compilacao, _, interface = GetBuildInfo()
  linhas[#linhas + 1] = string.format("Goblinomics %s · jogo %s (%s) · interface %s", VERSAO, tostring(versao), tostring(compilacao), tostring(interface))
  for _, grupo in ipairs(SONDAS) do
    local sim, nao = {}, {}
    for _, nome in ipairs(grupo[2]) do
      if existe(nome) then sim[#sim + 1] = nome else nao[#nao + 1] = nome end
    end
    linhas[#linhas + 1] = OURO .. grupo[1] .. "|r  " .. VERDE .. "tem:|r " .. (#sim > 0 and table.concat(sim, ", ") or "-")
      .. "  " .. VERMELHO .. "não tem:|r " .. (#nao > 0 and table.concat(nao, ", ") or "-")
  end
  -- As funções que o Auctionator oferece a outros addons, pelo nome.
  if existe("Auctionator.API.v1") then
    local nomes = {}
    for nome, valor in pairs(Auctionator.API.v1) do
      if type(valor) == "function" then nomes[#nomes + 1] = nome end
    end
    table.sort(nomes)
    linhas[#linhas + 1] = OURO .. "Auctionator.API.v1|r  " .. table.concat(nomes, ", ")
  end
  local libs = {}
  if LibStub and LibStub.GetLibrary then
    for _, nome in ipairs({"LibDBIcon-1.0", "LibDataBroker-1.1", "AceGUI-3.0"}) do
      if LibStub:GetLibrary(nome, true) then libs[#libs + 1] = nome end
    end
  end
  linhas[#linhas + 1] = OURO .. "Bibliotecas|r  " .. (#libs > 0 and table.concat(libs, ", ") or "-")
  return table.concat(linhas, "\n")
end

-- ---- Painel: abre pelo botão do minimapa ----

local painel, textoDiag

local function botao(pai, rotulo, largura, aoClicar)
  local b = CreateFrame("Button", nil, pai, "UIPanelButtonTemplate")
  b:SetSize(largura, 24)
  b:SetText(rotulo)
  b:SetScript("OnClick", aoClicar)
  return b
end

local function atualizarPainel()
  if not painel then return end
  painel.estado:SetText(resumo())
  painel.dica:SetText("Dados na dica do item: " .. (GoblinomicsOpcoes.dica == false and "desligados" or "ligados"))
  painel.aviso:SetText("Botão de preços velhos: " .. (GoblinomicsOpcoes.aviso and "ligado" or "desligado"))
end

local function criarPainel()
  painel = CreateFrame("Frame", "GoblinomicsPainel", UIParent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  painel:SetSize(560, 150)
  painel:SetPoint("CENTER", UIParent, "CENTER", 0, 120)
  painel:SetFrameStrata("DIALOG")
  if painel.SetBackdrop then
    painel:SetBackdrop({bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
      edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border", tile = true, tileSize = 32, edgeSize = 24,
      insets = {left = 6, right = 6, top = 6, bottom = 6}})
  else
    local fundo = painel:CreateTexture(nil, "BACKGROUND")
    fundo:SetAllPoints(painel)
    fundo:SetColorTexture(0, 0, 0, 0.85)
  end
  painel:EnableMouse(true)
  painel:SetMovable(true)
  painel:RegisterForDrag("LeftButton")
  painel:SetScript("OnDragStart", painel.StartMoving)
  painel:SetScript("OnDragStop", painel.StopMovingOrSizing)
  painel:SetClampedToScreen(true)
  -- Esc fecha, como as janelas do jogo.
  if UISpecialFrames then table.insert(UISpecialFrames, "GoblinomicsPainel") end

  local icone = painel:CreateTexture(nil, "ARTWORK")
  icone:SetSize(28, 28)
  icone:SetPoint("TOPLEFT", 16, -14)
  icone:SetTexture(ICONE)
  local titulo = painel:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
  titulo:SetPoint("LEFT", icone, "RIGHT", 8, 0)
  titulo:SetText("Goblinomics " .. VERSAO)
  painel.estado = painel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  painel.estado:SetPoint("TOPLEFT", 16, -48)

  botao(painel, "Fechar", 70, function() painel:Hide() end):SetPoint("TOPRIGHT", -14, -14)
  local recarrega = botao(painel, "Atualizar preços (recarrega a interface)", 270, recarregar)
  recarrega:SetPoint("TOPLEFT", 16, -68)
  painel.dica = botao(painel, "", 250, function()
    GoblinomicsOpcoes.dica = GoblinomicsOpcoes.dica == false
    atualizarPainel()
  end)
  painel.dica:SetPoint("TOPLEFT", 16, -98)
  painel.aviso = botao(painel, "", 250, function()
    GoblinomicsOpcoes.aviso = not GoblinomicsOpcoes.aviso
    dispensado = false
    conferir()
    atualizarPainel()
  end)
  painel.aviso:SetPoint("LEFT", painel.dica, "RIGHT", 8, 0)
  local diag = botao(painel, "Diagnóstico", 110, function()
    -- O texto aparece aqui mesmo, para caber numa captura de tela.
    if textoDiag:IsShown() then
      textoDiag:Hide()
      painel:SetHeight(150)
    else
      textoDiag:SetText(diagnostico())
      textoDiag:Show()
      painel:SetHeight(170 + textoDiag:GetStringHeight())
    end
  end)
  diag:SetPoint("LEFT", recarrega, "RIGHT", 8, 0)

  textoDiag = painel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  textoDiag:SetPoint("TOPLEFT", 16, -132)
  textoDiag:SetWidth(528)
  textoDiag:SetJustifyH("LEFT")
  if textoDiag.SetWordWrap then textoDiag:SetWordWrap(true) end
  textoDiag:Hide()
  painel:Hide()
end

local function alternarPainel()
  if not painel then criarPainel() end
  if painel:IsShown() then
    painel:Hide()
  else
    atualizarPainel()
    painel:Show()
  end
end

-- ---- Botão no minimapa: arrasta em volta dele, a posição fica guardada ----

local function posicionar(b)
  local angulo = math.rad(GoblinomicsOpcoes.angulo or 215)
  local raio = (Minimap:GetWidth() / 2) + 5
  b:ClearAllPoints()
  b:SetPoint("CENTER", Minimap, "CENTER", math.cos(angulo) * raio, math.sin(angulo) * raio)
end

local function criarBotaoDoMinimapa()
  if not Minimap then return end
  local b = CreateFrame("Button", "GoblinomicsMinimapa", Minimap)
  b:SetSize(31, 31)
  b:SetFrameStrata("MEDIUM")
  b:SetFrameLevel(8)
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  b:RegisterForDrag("LeftButton")
  b:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
  local icone = b:CreateTexture(nil, "BACKGROUND")
  icone:SetSize(21, 21)
  icone:SetPoint("CENTER", 0, 0)
  icone:SetTexture(ICONE)
  local borda = b:CreateTexture(nil, "OVERLAY")
  borda:SetSize(53, 53)
  borda:SetPoint("TOPLEFT", 0, 0)
  borda:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")

  b:SetScript("OnClick", function(_, tecla)
    if tecla == "RightButton" then
      recarregar()
    elseif G.alternarJanela then
      -- Se a janela der erro ao abrir, o painel de opções ainda abre.
      local ok, erro = pcall(G.alternarJanela)
      if not ok then
        dizer("a janela falhou: " .. tostring(erro))
        alternarPainel()
      end
    else
      alternarPainel()
    end
  end)
  b:SetScript("OnDragStart", function(self)
    self:SetScript("OnUpdate", function(eu)
      local cx, cy = Minimap:GetCenter()
      local x, y = GetCursorPosition()
      local escala = Minimap:GetEffectiveScale()
      GoblinomicsOpcoes.angulo = math.deg(math.atan2(y / escala - cy, x / escala - cx))
      posicionar(eu)
    end)
  end)
  b:SetScript("OnDragStop", function(self) self:SetScript("OnUpdate", nil) end)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:AddLine("Goblinomics " .. VERSAO)
    GameTooltip:AddLine(resumo(), 1, 1, 1, true)
    GameTooltip:AddLine(" ")
    GameTooltip:AddLine("Clique: abre a janela.", 0.78, 0.78, 0.78)
    GameTooltip:AddLine("Clique direito: recarrega para ler os preços novos.", 0.78, 0.78, 0.78)
    GameTooltip:AddLine("Arraste: muda o botão de lugar.", 0.78, 0.78, 0.78)
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", function() GameTooltip:Hide() end)
  posicionar(b)
end

-- O que a Janela.lua usa daqui.
G.VERSAO, G.D, G.ICONE = VERSAO, D, ICONE
G.dizer, G.moeda, G.numero, G.resumo, G.recarregar, G.alternarPainel = dizer, moeda, numero, resumo, recarregar, alternarPainel
G.precoDoScan, G.QUEM_CHAMA = precoDoScan, QUEM_CHAMA

-- ---- Entrada no jogo ----

local quadro = CreateFrame("Frame")
quadro:RegisterEvent("PLAYER_LOGIN")
quadro:SetScript("OnEvent", function()
  if type(GoblinomicsOpcoes) ~= "table" then GoblinomicsOpcoes = {} end
  if GoblinomicsOpcoes.aviso == nil then GoblinomicsOpcoes.aviso = true end
  -- Cada peça por si: um erro numa não impede as outras de aparecer.
  local ok, erro = pcall(criarBotaoDoMinimapa)
  if not ok then dizer("o botão do minimapa falhou: " .. tostring(erro)) end
  if not D then
    dizer("sem dados. Rode o atualizar.bat da pasta do addon e recarregue.")
    return
  end
  dizer(resumo() .. ". Clique na moeda do minimapa para abrir a janela.")
  ok, erro = pcall(criarAviso)
  if not ok then dizer("o botão de aviso falhou: " .. tostring(erro)) end
  conferir()
  if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(60, conferir) end
end)

-- Os comandos continuam existindo, mas tudo está no painel.
SLASH_GOBLINOMICS1 = "/gob"
SLASH_GOBLINOMICS2 = "/goblinomics"
SlashCmdList["GOBLINOMICS"] = function(texto)
  texto = string.lower(texto or "")
  if texto == "aviso" then
    GoblinomicsOpcoes.aviso = not GoblinomicsOpcoes.aviso
    dispensado = false
    dizer("botão de preços velhos " .. (GoblinomicsOpcoes.aviso and "ligado." or "desligado."))
    conferir()
  elseif texto == "atualizar" or texto == "reload" then
    recarregar()
  elseif texto == "teste" then
    if not aviso then
      dizer("sem dados carregados, não há botão para mostrar.")
    else
      emTeste = true
      conferir()
      dizer("o botão está no alto da tela, no centro. Neste teste, clicar nele só o esconde.")
    end
  elseif texto == "diag" then
    for linha in string.gmatch(diagnostico(), "[^\n]+") do dizer(linha) end
  elseif texto == "opcoes" or texto == "opções" then
    alternarPainel()
  else
    dizer("versão " .. VERSAO .. ". " .. resumo() .. ".")
    if G.alternarJanela then G.alternarJanela() else alternarPainel() end
  end
end
