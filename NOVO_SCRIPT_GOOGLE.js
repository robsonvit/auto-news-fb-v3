function acordarBotGithub() {
  // A URL do seu novo repositório na nova conta do GitHub
  var url = "https://api.github.com/repos/robsonvit/auto-news-fb-v3/actions/workflows/facebook_news_bot.yml/dispatches";
  
  var payload = {
    "ref": "master"
  };
  
  var options = {
    "method": "post",
    "headers": {
      // O token abaixo foi gerado agora especialmente para este novo repositório
      "Authorization": "Bearer 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", 
      "Accept": "application/vnd.github.v3+json"
    },
    "payload": JSON.stringify(payload)
  };
  
  try {
    var response = UrlFetchApp.fetch(url, options);
    Logger.log(response.getContentText());
  } catch (e) {
    Logger.log("Erro: " + e.toString());
  }
}
