-- Janela do Goblinomics (GoblinomicsJanela): Resumo, Ofertas, Profissões e Coleta, com os dados do Dados.lua.
-- Abre pela moeda do minimapa. Fica num arquivo à parte: se algo aqui falhar, a dica do item continua.

local _, G = ...
if not G or not G.D then return end
local D = G.D
local dizer, moeda, numero = G.dizer, G.moeda, G.numero
local OURO, CINZA, VERDE, BRANCO = "|cffffd100", "|cff9d9d9d", "|cff40ff40", "|cffffffff"
local LINHAS, ALTURA = 15, 22
local TAXA = 0.05

local janela, abaAtual, linhasDaAba, deslocamento, selecionada = nil, "resumo", {}, 0, nil

-- ---- Dados ----

local function nome(id)
  return (D.nomes and D.nomes[id]) or ("item " .. id)
end

local function meuNome()
  local eu = UnitName and UnitName("player")
  return eu or ""
end

-- A lista "|Nome|Nome|" tem o personagem? O nome do jogo pode vir sem o sobrenome, então basta começar igual.
local function euSei(quem)
  local eu = meuNome()
  return quem ~= nil and eu ~= "" and string.find(quem, "|" .. eu, 1, true) ~= nil
end

local function iconeDe(id)
  local busca = (C_Item and C_Item.GetItemIconByID) or GetItemIcon
  if not busca then return nil end
  local ok, textura = pcall(busca, id)
  return ok and textura or nil
end

local function zonaAtual()
  local a = GetRealZoneText and GetRealZoneText() or ""
  local b = GetZoneText and GetZoneText() or ""
  return a, b
end

-- Receitas com lucro agora e com saída, da que mais rende por dia para a que menos.
local function receitas(soMinhas)
  local saida = {}
  for id, f in pairs(D.fab or {}) do
    local i = D.itens[id]
    if i and i.l and i.l > 0 and i.d and i.d >= 1 and (not soMinhas or euSei(f.q)) then
      saida[#saida + 1] = {id = id, f = f, i = i, porDia = i.l * i.d}
    end
  end
  table.sort(saida, function(a, b) return a.porDia > b.porDia end)
  return saida
end

-- Mapas para a profissão ("e" ervas, "m" minérios), do maior valor médio para o menor. O valor médio é o
-- dos materiais comuns com venda, sem a taxa do leilão, como na aba Coleta do site.
local function mapas(tipo)
  local saida = {}
  for _, z in ipairs(D.coleta or {}) do
    local ids = z[tipo]
    if ids then
      local soma, n, itens = 0, 0, {}
      for _, id in ipairs(ids) do
        local i = D.itens[id]
        if i and i.m then
          itens[#itens + 1] = {id = id, valor = i.m * (1 - TAXA)}
          if i.d and i.d > 0 then soma, n = soma + i.m * (1 - TAXA), n + 1 end
        end
      end
      table.sort(itens, function(a, b) return a.valor > b.valor end)
      if #itens > 0 then
        saida[#saida + 1] = {z = z.z, nv = z.nv, itens = itens, media = n > 0 and soma / n or 0}
      end
    end
  end
  table.sort(saida, function(a, b) return a.media > b.media end)
  return saida
end

-- ---- Auctionator: cria a lista de compras lá dentro ----

local function listaNoAuctionator(nomeDaLista, termos)
  local api = Auctionator and Auctionator.API and Auctionator.API.v1
  if not api or not api.CreateShoppingList then
    dizer("o Auctionator não está disponível para criar a lista.")
    return
  end
  if #termos == 0 then
    dizer("nada para pôr na lista.")
    return
  end
  local buscas = {}
  for _, t in ipairs(termos) do
    local busca
    if api.ConvertToSearchString then
      local ok, texto = pcall(api.ConvertToSearchString, G.QUEM_CHAMA, {searchString = t.nome, isExact = true, quantity = t.q})
      if ok and type(texto) == "string" then busca = texto end
    end
    -- Sem a conversão do Auctionator: o nome entre aspas é busca exata.
    buscas[#buscas + 1] = busca or ('"' .. t.nome .. '"')
  end
  local ok, erro = pcall(api.CreateShoppingList, G.QUEM_CHAMA, nomeDaLista, buscas)
  if ok then
    dizer(VERDE .. "lista criada no Auctionator:|r " .. nomeDaLista .. " (" .. #buscas .. " itens). Abra o leilão, aba Shopping.")
  else
    dizer("o Auctionator recusou a lista: " .. tostring(erro))
  end
end

-- ---- Conteúdo de cada aba: {texto do cabeçalho, linhas} ----
-- Linha: id (item), esq, meio, dir, titulo (linha de seção), dica (função que preenche a dica), dados.

local opcoes = {soMinhas = true, tipoDeColeta = "e"}

local function linhaDeReceita(r)
  return {id = r.id, esq = nome(r.id), meio = VERDE .. "+" .. moeda(r.i.l) .. "|r",
    dir = CINZA .. r.f.p .. " · ~" .. numero(r.i.d, true) .. "/dia|r", receita = r}
end

local function linhaDeOferta(id)
  local i = D.itens[id]
  if not i or not i.m or not i.h then return nil end
  local pct = math.floor((i.m - i.h) / i.h * 100 + 0.5)
  return {id = id, esq = nome(id), meio = moeda(i.m) .. VERDE .. " (" .. pct .. "%)|r",
    dir = CINZA .. "média " .. moeda(i.h) .. CINZA .. " · ~" .. numero(i.d or 0, true) .. "/dia|r"}
end

local function linhaDeMapa(m, posicao, aqui)
  local nomes = {}
  for k = 1, math.min(3, #m.itens) do nomes[#nomes + 1] = nome(m.itens[k].id) end
  local marca = aqui and (VERDE .. "> ") or (CINZA .. posicao .. ". |r")
  return {esq = marca .. (aqui and "" or BRANCO) .. m.z .. "|r" .. (m.nv ~= "" and (CINZA .. " " .. m.nv .. "|r") or ""),
    meio = moeda(m.media), dir = CINZA .. table.concat(nomes, ", ") .. (#m.itens > 3 and (" +" .. (#m.itens - 3)) or "") .. "|r",
    dica = function(dica)
      dica:AddLine(m.z)
      for _, item in ipairs(m.itens) do dica:AddDoubleLine(nome(item.id), moeda(item.valor), 1, 1, 1, 1, 1, 1) end
      dica:AddLine("Valor por unidade, sem a taxa do leilão.", 0.6, 0.6, 0.6, true)
    end}
end

local function mapasComAqui(tipo)
  local lista, a, b = mapas(tipo), zonaAtual()
  local linhas = {}
  for posicao, m in ipairs(lista) do
    local aqui = m.z == a or m.z == b
    local linha = linhaDeMapa(m, posicao, aqui)
    -- O mapa em que a pessoa está sobe para o topo.
    if aqui then table.insert(linhas, 1, linha) else linhas[#linhas + 1] = linha end
  end
  return linhas
end

local ABAS = {
  {chave = "resumo", rotulo = "Resumo", montar = function()
    local linhas = {}
    linhas[#linhas + 1] = {titulo = "Fabricar agora (receitas que este personagem sabe)"}
    local minhas = receitas(true)
    for k = 1, math.min(4, #minhas) do linhas[#linhas + 1] = linhaDeReceita(minhas[k]) end
    if #minhas == 0 then linhas[#linhas + 1] = {esq = CINZA .. "Nenhuma receita sua com lucro agora (ou o site ainda não leu este personagem).|r"} end
    linhas[#linhas + 1] = {titulo = "Pechinchas no leilão"}
    local n = 0
    for _, id in ipairs(D.ofertas or {}) do
      local linha = linhaDeOferta(id)
      if linha and n < 4 then linhas[#linhas + 1] = linha; n = n + 1 end
    end
    if n == 0 then linhas[#linhas + 1] = {esq = CINZA .. "Nenhuma pechincha agora.|r"} end
    linhas[#linhas + 1] = {titulo = "Coleta: melhores mapas de ervas"}
    local ervas = mapasComAqui("e")
    for k = 1, math.min(3, #ervas) do linhas[#linhas + 1] = ervas[k] end
    return G.resumo() .. ". Passe o mouse numa linha para ver o item.", linhas
  end},
  {chave = "ofertas", rotulo = "Ofertas", montar = function()
    local linhas = {}
    for _, id in ipairs(D.ofertas or {}) do
      local linha = linhaDeOferta(id)
      if linha then linhas[#linhas + 1] = linha end
    end
    return "30% ou mais abaixo da média de 7 dias, vendendo 10 ou mais por dia. Anúncio não é venda: confira antes de comprar.", linhas
  end, acao = {rotulo = "Mandar tudo para o Auctionator", fazer = function(linhas)
    local termos = {}
    for _, l in ipairs(linhas) do if l.id then termos[#termos + 1] = {nome = nome(l.id)} end end
    listaNoAuctionator("Goblinomics: ofertas", termos)
  end}},
  {chave = "profissoes", rotulo = "Profissões", montar = function()
    local linhas = {}
    for _, r in ipairs(receitas(opcoes.soMinhas)) do linhas[#linhas + 1] = linhaDeReceita(r) end
    local quais = opcoes.soMinhas and ("só as que " .. (meuNome() ~= "" and meuNome() or "este personagem") .. " sabe") or "todas"
    return "Receitas com lucro agora, " .. quais .. ". Clique numa receita para escolhê-la; o lucro é por unidade.", linhas
  end, alternar = {rotulo = function() return opcoes.soMinhas and "Mostrar todas" or "Só as que eu sei" end,
    fazer = function() opcoes.soMinhas = not opcoes.soMinhas end},
  acao = {rotulo = "Materiais da escolhida para o Auctionator", fazer = function()
    if not selecionada or not selecionada.receita then
      dizer("clique primeiro numa receita da lista.")
      return
    end
    local r, termos, doNpc = selecionada.receita, {}, {}
    for k = 1, #r.f.m, 2 do
      local material, quantidade = r.f.m[k], r.f.m[k + 1]
      local noLeilao = D.itens[material] and D.itens[material].m
      local npc = D.npc and D.npc[material]
      -- O que o vendedor NPC tem mais barato não vai para a lista do leilão.
      if npc and (not noLeilao or npc <= noLeilao) then
        doNpc[#doNpc + 1] = quantidade .. " x " .. nome(material)
      else
        termos[#termos + 1] = {nome = nome(material), q = quantidade}
      end
    end
    listaNoAuctionator("Goblinomics: " .. nome(r.id), termos)
    if #doNpc > 0 then dizer("compre no vendedor NPC: " .. table.concat(doNpc, ", ") .. ".") end
  end}},
  {chave = "coleta", rotulo = "Coleta", montar = function()
    local a = zonaAtual()
    return "Mapas pelo valor médio do que nasce em cada um (QuestieDB). Você está em " .. (a ~= "" and a or "?")
      .. ". Passe o mouse para ver todos os materiais do mapa.", mapasComAqui(opcoes.tipoDeColeta)
  end, alternar = {rotulo = function() return opcoes.tipoDeColeta == "e" and "Ver minérios" or "Ver ervas" end,
    fazer = function() opcoes.tipoDeColeta = opcoes.tipoDeColeta == "e" and "m" or "e" end}},
}

local function abaDe(chave)
  for _, a in ipairs(ABAS) do if a.chave == chave then return a end end
  return ABAS[1]
end

-- ---- Desenho ----

local function desenhar()
  if not janela then return end
  local aba = abaDe(abaAtual)
  local maximo = math.max(0, #linhasDaAba - LINHAS)
  if deslocamento > maximo then deslocamento = maximo end
  if deslocamento < 0 then deslocamento = 0 end
  for k = 1, LINHAS do
    local linha, dados = janela.linhas[k], linhasDaAba[k + deslocamento]
    linha.dados = dados
    if dados then
      local textura = dados.id and iconeDe(dados.id)
      if textura then linha.icone:SetTexture(textura); linha.icone:Show() else linha.icone:Hide() end
      linha.esq:SetText(dados.titulo and (OURO .. dados.titulo .. "|r") or (dados.esq or ""))
      linha.meio:SetText(dados.meio or "")
      linha.dir:SetText(dados.dir or "")
      if dados == selecionada then linha.fundo:Show() else linha.fundo:Hide() end
      linha:Show()
    else
      linha:Hide()
    end
  end
  janela.pagina:SetText(#linhasDaAba > LINHAS
    and string.format("%d-%d de %d (role para ver mais)", deslocamento + 1, math.min(deslocamento + LINHAS, #linhasDaAba), #linhasDaAba) or "")
  for _, b in ipairs(janela.abas) do
    if b.chave == abaAtual then b:LockHighlight() else b:UnlockHighlight() end
  end
  if aba.acao then janela.acao:SetText(aba.acao.rotulo); janela.acao:Show() else janela.acao:Hide() end
  if aba.alternar then janela.alternar:SetText(aba.alternar.rotulo()); janela.alternar:Show() else janela.alternar:Hide() end
end

local function montar()
  local aba = abaDe(abaAtual)
  local ok, cabecalho, linhas = pcall(aba.montar)
  if not ok then
    dizer("a aba " .. aba.rotulo .. " falhou: " .. tostring(cabecalho))
    cabecalho, linhas = "Esta aba deu erro; a mensagem está no chat.", {}
  end
  linhasDaAba = linhas or {}
  janela.cabecalho:SetText(cabecalho or "")
  desenhar()
end

local function trocarAba(chave)
  abaAtual, deslocamento, selecionada = chave, 0, nil
  montar()
end

local function botao(pai, rotulo, largura, aoClicar)
  local b = CreateFrame("Button", nil, pai, "UIPanelButtonTemplate")
  b:SetSize(largura, 22)
  b:SetText(rotulo)
  b:SetScript("OnClick", aoClicar)
  return b
end

local function criarLinha(k)
  local linha = CreateFrame("Button", nil, janela)
  linha:SetSize(668, ALTURA)
  linha:SetPoint("TOPLEFT", 16, -96 - (k - 1) * ALTURA)
  linha.fundo = linha:CreateTexture(nil, "BACKGROUND")
  linha.fundo:SetAllPoints(linha)
  linha.fundo:SetColorTexture(1, 0.82, 0, 0.18)
  linha.fundo:Hide()
  local realce = linha:CreateTexture(nil, "HIGHLIGHT")
  realce:SetAllPoints(linha)
  realce:SetColorTexture(1, 1, 1, 0.08)
  linha.icone = linha:CreateTexture(nil, "ARTWORK")
  linha.icone:SetSize(18, 18)
  linha.icone:SetPoint("LEFT", 2, 0)
  linha.esq = linha:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  linha.esq:SetPoint("LEFT", 26, 0)
  linha.esq:SetWidth(270)
  linha.esq:SetJustifyH("LEFT")
  linha.meio = linha:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  linha.meio:SetPoint("LEFT", 300, 0)
  linha.meio:SetWidth(140)
  linha.meio:SetJustifyH("RIGHT")
  linha.dir = linha:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  linha.dir:SetPoint("LEFT", 452, 0)
  linha.dir:SetWidth(214)
  linha.dir:SetJustifyH("LEFT")
  for _, texto in ipairs({linha.esq, linha.meio, linha.dir}) do
    if texto.SetWordWrap then texto:SetWordWrap(false) end
  end
  linha:SetScript("OnEnter", function(self)
    local dados = self.dados
    if not dados or (not dados.id and not dados.dica) then return end
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    if dados.dica then
      dados.dica(GameTooltip)
    else
      -- A dica do próprio item, que já traz as linhas do Goblinomics.
      local ok = pcall(GameTooltip.SetHyperlink, GameTooltip, "item:" .. dados.id)
      if not ok then GameTooltip:AddLine(nome(dados.id)) end
    end
    GameTooltip:Show()
  end)
  linha:SetScript("OnLeave", function() GameTooltip:Hide() end)
  linha:SetScript("OnClick", function(self)
    if self.dados and self.dados.id then
      selecionada = self.dados
      desenhar()
    end
  end)
  return linha
end

local function criar()
  janela = CreateFrame("Frame", "GoblinomicsJanela", UIParent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  janela:SetSize(700, 480)
  janela:SetPoint("CENTER", UIParent, "CENTER", 0, 40)
  janela:SetFrameStrata("HIGH")
  if janela.SetBackdrop then
    janela:SetBackdrop({bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background-Dark",
      edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border", tile = true, tileSize = 32, edgeSize = 24,
      insets = {left = 6, right = 6, top = 6, bottom = 6}})
  else
    local fundo = janela:CreateTexture(nil, "BACKGROUND")
    fundo:SetAllPoints(janela)
    fundo:SetColorTexture(0, 0, 0, 0.9)
  end
  janela:EnableMouse(true)
  janela:SetMovable(true)
  janela:RegisterForDrag("LeftButton")
  janela:SetScript("OnDragStart", janela.StartMoving)
  janela:SetScript("OnDragStop", janela.StopMovingOrSizing)
  janela:SetClampedToScreen(true)
  if UISpecialFrames then table.insert(UISpecialFrames, "GoblinomicsJanela") end
  janela:EnableMouseWheel(true)
  janela:SetScript("OnMouseWheel", function(_, sentido)
    deslocamento = deslocamento - sentido * 3
    desenhar()
  end)

  local icone = janela:CreateTexture(nil, "ARTWORK")
  icone:SetSize(26, 26)
  icone:SetPoint("TOPLEFT", 16, -14)
  icone:SetTexture(G.ICONE)
  local titulo = janela:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
  titulo:SetPoint("LEFT", icone, "RIGHT", 8, 0)
  titulo:SetText("Goblinomics")

  botao(janela, "Fechar", 70, function() janela:Hide() end):SetPoint("TOPRIGHT", -14, -14)
  botao(janela, "Opções", 70, function() G.alternarPainel() end):SetPoint("TOPRIGHT", -88, -14)
  botao(janela, "Atualizar preços", 120, function() G.recarregar() end):SetPoint("TOPRIGHT", -162, -14)

  janela.abas = {}
  for k, aba in ipairs(ABAS) do
    local b = botao(janela, aba.rotulo, 100, function() trocarAba(aba.chave) end)
    b:SetPoint("TOPLEFT", 16 + (k - 1) * 104, -46)
    b.chave = aba.chave
    janela.abas[k] = b
  end

  janela.cabecalho = janela:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  janela.cabecalho:SetPoint("TOPLEFT", 16, -72)
  janela.cabecalho:SetWidth(668)
  janela.cabecalho:SetJustifyH("LEFT")

  janela.linhas = {}
  for k = 1, LINHAS do janela.linhas[k] = criarLinha(k) end

  janela.pagina = janela:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  janela.pagina:SetPoint("BOTTOMRIGHT", -16, 20)
  janela.acao = botao(janela, "", 290, function()
    local aba = abaDe(abaAtual)
    if aba.acao then
      local ok, erro = pcall(aba.acao.fazer, linhasDaAba)
      if not ok then dizer("não deu certo: " .. tostring(erro)) end
    end
  end)
  janela.acao:SetPoint("BOTTOMLEFT", 16, 14)
  janela.alternar = botao(janela, "", 140, function()
    local aba = abaDe(abaAtual)
    if aba.alternar then
      aba.alternar.fazer()
      deslocamento, selecionada = 0, nil
      montar()
    end
  end)
  janela.alternar:SetPoint("LEFT", janela.acao, "RIGHT", 8, 0)
  janela:Hide()
end

function G.alternarJanela()
  if not janela then criar() end
  if janela:IsShown() then
    janela:Hide()
  else
    montar()
    janela:Show()
  end
end

-- ---- No vendedor: o que ele vende que rende no leilão ----

local function precoNoVendedor(k)
  -- A interface nova devolve uma tabela; a antiga, vários valores.
  if C_MerchantFrame and C_MerchantFrame.GetItemInfo then
    local info = C_MerchantFrame.GetItemInfo(k)
    if info then return info.price, info.stackCount or 1, info.numAvailable end
  end
  if GetMerchantItemInfo then
    local _, _, preco, lote, disponiveis = GetMerchantItemInfo(k)
    return preco, lote or 1, disponiveis
  end
  return nil
end

local function olharVendedor()
  if not GetMerchantNumItems or not GetMerchantItemLink then return end
  local achados = {}
  for k = 1, GetMerchantNumItems() do
    local link = GetMerchantItemLink(k)
    local id = link and tonumber(string.match(link, "item:(%d+)"))
    local i = id and D.itens[id]
    local preco, lote, disponiveis = precoNoVendedor(k)
    if i and i.m and preco and preco > 0 then
      local custo = preco / (lote or 1)
      local lucro = i.m * (1 - TAXA) - custo
      -- Só o que tem saída e sobra de pelo menos 20% sobre o que se paga aqui.
      if i.d and i.d >= 1 and lucro > custo * 0.2 then
        achados[#achados + 1] = {link = link, custo = custo, venda = i.m, lucro = lucro, d = i.d, limitado = disponiveis and disponiveis > 0}
      end
    end
  end
  if #achados == 0 then return end
  table.sort(achados, function(a, b) return a.lucro > b.lucro end)
  dizer("este vendedor tem " .. #achados .. (#achados == 1 and " item que rende" or " itens que rendem") .. " no leilão:")
  for k = 1, math.min(5, #achados) do
    local a = achados[k]
    dizer("  " .. a.link .. " custa " .. moeda(a.custo) .. ", vende a " .. moeda(a.venda) .. " (~" .. numero(a.d, true) .. "/dia)"
      .. (a.limitado and (OURO .. " · estoque limitado|r") or ""))
  end
end

local quadro = CreateFrame("Frame")
quadro:RegisterEvent("MERCHANT_SHOW")
quadro:SetScript("OnEvent", function()
  if GoblinomicsOpcoes and GoblinomicsOpcoes.vendedor == false then return end
  local ok, erro = pcall(olharVendedor)
  if not ok then dizer("a leitura do vendedor falhou: " .. tostring(erro)) end
end)
