$(function () {

	// TODO: http://www.highcharts.com/stock/demo/data-grouping



	// TODO
    //$.getJSON('kahviraspi/index.html?q=', function (data) {
    $.getJSON('https://www.highcharts.com/samples/data/jsonp.php?filename=aapl-c.json&callback=?', function (data) {
        // Create the chart
        $('#container').highcharts('StockChart', {


            rangeSelector: {
                selected: 1
            },

            title: {
                text: 'Kahvin määrä kiltiksellä ajan funktiona'
            },

            series: [{
                name: 'kahvi',
                data: data,
                tooltip: {
                    valueDecimals: 2
                }
            }]
        });
    });

});

