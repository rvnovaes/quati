function getMessage (name, version){
    var browserVersions = document.getElementById("browserVersions");
    var acceptedBrowsers = {};
    for (i=0; i < browserVersions.childElementCount; i++) {
        var browserArray = browserVersions.children[i].textContent.split(' ');
        acceptedBrowsers[browserArray[0].toLowerCase()] = parseInt(browserArray[1]);
    }

    var message = false;

    var errorDetail = '<p style="font-size: 10px">Versões antigas de navegadores podem não suportar recursos como ' +
        'JavaScript, Ajax, jQuery, HTML, CSS, etc, impedindo que páginas de sites que possuam esses recursos abram ' +
        'corretamente. Alguns exemplos de problemas: não carregar todo o conteúdo do site, quebrar o layout, não ' +
        'carregar alguma funcionalidade impedindo a execução de uma tarefa ou até apresentar erros. Para evitar esses ' +
        'possíveis problemas, os fabricantes dos navegadores estão constantemente atualizando seus produtos para ' +
        'suportar novos recursos. É recomendado que você mantenha seu navegador sempre na versão mais atual.</p>';

    if (! acceptedBrowsers[name]) {
        message = '<p><b>Esse navegador é incompatível com o Quati. Os navegadores compatíveis são:</b></p>' +
        browserVersions.outerHTML;
    } else if (version < acceptedBrowsers[name]) {
        message = '<p><b>A versão ' + version + ' desse navegador não é compatível com o Quati. ' +
            'Para usar o sistema a versão deve ser atualizada para ' + acceptedBrowsers[name] + ' ou posterior.</b></p>' +
            errorDetail;
    }
    return message;
}

function getBrowser(){
    var browserName = '';
    var browserVersion = '';
    var ua = navigator.userAgent, tem, M = ua.match(/(edge(?=\/))\/?\s*(\d+)/i) || [];
    if (! M.length) {
        ua = navigator.userAgent, tem, M = ua.match(/(opera|chrome|safari|firefox|msie|trident(?=\/))\/?\s*(\d+)/i) || [];
    }
    if(/trident/i.test(M[1])){
        tem=/\brv[ :]+(\d+)/g.exec(ua) || [];
        browserName = 'IE';
        browserVersion = (tem[1]||'');
    }
    if(M[1]==='Chrome'){
        tem=ua.match(/\bOPR\/(\d+)/)
        if(tem!=null) {
            browserName = 'Opera';
            browserVersion = tem[1];
        }
    }
    M=M[2]? [M[1], M[2]]: [navigator.appName, navigator.appVersion, '-?'];
    if((tem=ua.match(/version\/(\d+)/i))!=null) {M.splice(1,1,tem[1]);}
    if (! browserName) {
        browserName = M[0];
        browserVersion = M[1];
    }
    return {
        name: browserName,
        version: browserVersion,
        message: getMessage(browserName.toLowerCase(), browserVersion)
    };
 }